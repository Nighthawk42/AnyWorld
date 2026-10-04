"use strict";

const audioState = {
    enabled: false,
    healthy: false,
    mediaRecorder: null,
    audioChunks: [],
    isRecording: false,
    activeAudio: null,
    activeButton: null,
};

async function initAudio() {
    try {
        const response = await fetch("/api/audio/status");
        if (!response.ok) return;
        const data = await response.json();
        audioState.enabled = Boolean(data.enabled);
        audioState.healthy = Boolean(data.healthy);

        if (audioState.enabled && elements.micButton) {
            const hasMedia = Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
            if (hasMedia) {
                elements.micButton.hidden = false;
                setupMicrophone();
            }
        }
    } catch {
        // Audio backend not available or offline; remain silent
    }
}

function setupMicrophone() {
    const mic = elements.micButton;
    if (!mic) return;

    let holdTimeout = null;
    let isHolding = false;

    async function startRecording() {
        if (audioState.isRecording) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioState.audioChunks = [];
            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : (MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "");

            const options = mimeType ? { mimeType } : {};
            const recorder = new MediaRecorder(stream, options);

            recorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    audioState.audioChunks.push(event.data);
                }
            };

            recorder.onstop = async () => {
                stream.getTracks().forEach((track) => track.stop());
                mic.classList.remove("recording");
                audioState.isRecording = false;

                if (audioState.audioChunks.length === 0) return;
                const audioBlob = new Blob(audioState.audioChunks, {
                    type: mimeType || "audio/webm",
                });
                await sendTranscription(audioBlob);
            };

            audioState.mediaRecorder = recorder;
            recorder.start();
            audioState.isRecording = true;
            mic.classList.add("recording");
            elements.actionInput.placeholder = "Listening... (release or click to submit voice)";
        } catch (err) {
            mic.classList.remove("recording");
            audioState.isRecording = false;
        }
    }

    function stopRecording() {
        if (!audioState.isRecording || !audioState.mediaRecorder) return;
        if (audioState.mediaRecorder.state !== "inactive") {
            audioState.mediaRecorder.stop();
        }
    }

    async function sendTranscription(blob) {
        const formData = new FormData();
        const ext = blob.type.includes("webm") ? "webm" : "wav";
        formData.append("file", blob, `voice.${ext}`);

        elements.actionInput.placeholder = "Transcribing speech...";
        try {
            const response = await fetch("/api/audio/transcribe", {
                method: "POST",
                body: formData,
            });
            if (response.ok) {
                const data = await response.json();
                if (data.text) {
                    const current = elements.actionInput.value.trim();
                    elements.actionInput.value = current ? `${current} ${data.text}` : data.text;
                }
            }
        } catch {
            // Transcription network error
        } finally {
            elements.actionInput.placeholder = "Enter your action...";
            elements.actionInput.focus();
        }
    }

    // Support both press-and-hold and click toggle
    mic.addEventListener("pointerdown", (e) => {
        if (mic.disabled) return;
        isHolding = false;
        holdTimeout = setTimeout(() => {
            isHolding = true;
            startRecording();
        }, 200);
    });

    mic.addEventListener("pointerup", (e) => {
        if (holdTimeout) clearTimeout(holdTimeout);
        if (isHolding) {
            stopRecording();
            isHolding = false;
        } else if (!audioState.isRecording) {
            startRecording();
        } else {
            stopRecording();
        }
    });

    mic.addEventListener("pointercancel", () => {
        if (holdTimeout) clearTimeout(holdTimeout);
        if (audioState.isRecording) stopRecording();
        isHolding = false;
    });
}

function attachTTSButton(entryElement, text) {
    if (!audioState.enabled || !text || !text.trim()) return;

    const label = entryElement.querySelector(".state-round-label");
    if (!label) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tts-btn";
    btn.title = "Listen to narration";
    btn.setAttribute("aria-label", "Listen to narration");
    btn.textContent = "🔊 Listen";

    btn.addEventListener("click", () => {
        toggleSpeech(text, btn);
    });

    label.appendChild(btn);

    if (audioState.autoNarrate && !audioState.activeAudio) {
        toggleSpeech(text, btn);
    }
}

async function toggleSpeech(text, btn) {
    if (audioState.activeAudio && audioState.activeButton === btn) {
        audioState.activeAudio.pause();
        audioState.activeAudio = null;
        audioState.activeButton = null;
        btn.textContent = "🔊 Listen";
        btn.classList.remove("playing");
        return;
    }

    if (audioState.activeAudio) {
        audioState.activeAudio.pause();
        if (audioState.activeButton) {
            audioState.activeButton.textContent = "🔊 Listen";
            audioState.activeButton.classList.remove("playing");
        }
        audioState.activeAudio = null;
        audioState.activeButton = null;
    }

    btn.textContent = "⏳ Loading...";
    try {
        const response = await fetch("/api/audio/speech", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });

        if (!response.ok) {
            btn.textContent = "🔊 Listen";
            return;
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);

        audioState.activeAudio = audio;
        audioState.activeButton = btn;

        btn.textContent = "⏹️ Stop";
        btn.classList.add("playing");

        audio.onended = () => {
            btn.textContent = "🔊 Listen";
            btn.classList.remove("playing");
            audioState.activeAudio = null;
            audioState.activeButton = null;
            URL.revokeObjectURL(url);
        };

        audio.onerror = () => {
            btn.textContent = "🔊 Listen";
            btn.classList.remove("playing");
            audioState.activeAudio = null;
            audioState.activeButton = null;
            URL.revokeObjectURL(url);
        };

        await audio.play();
    } catch {
        btn.textContent = "🔊 Listen";
        btn.classList.remove("playing");
    }
}

function setTTSAuto(enabled) {
    audioState.autoNarrate = Boolean(enabled);
    try {
        localStorage.setItem("anyworld_tts_auto", audioState.autoNarrate ? "true" : "false");
    } catch {
        // Local storage unavailable
    }
}

function isTTSAuto() {
    return Boolean(audioState.autoNarrate);
}

try {
    audioState.autoNarrate = localStorage.getItem("anyworld_tts_auto") === "true";
} catch {
    audioState.autoNarrate = false;
}

// Expose globals for other modules
window.initAudio = initAudio;
window.attachTTSButton = attachTTSButton;
window.setTTSAuto = setTTSAuto;
window.isTTSAuto = isTTSAuto;
