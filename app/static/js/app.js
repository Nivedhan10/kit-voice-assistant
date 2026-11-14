/**
 * Main application client logic for KIT Voice Assistant.
 */

const recorder = new window.AudioRecorder();
let isMicActive = false;
let currentAudioPlayer = null;

// DOM Elements
const micBtn = document.getElementById("mic-btn");
const statusText = document.getElementById("status-text");
const conversationContainer = document.getElementById("conversation-container");
const confirmationContainer = document.getElementById("confirmation-container");
const waveCanvas = document.getElementById("voice-wave");

// Attach live waveform canvas to recorder if present
if (waveCanvas) {
  recorder.attachCanvas(waveCanvas);
}

// Update status text
function setStatus(text, isRecording = false) {
  if (statusText) statusText.innerText = text;
  if (micBtn) {
    if (isRecording) {
      micBtn.classList.add("recording");
    } else {
      micBtn.classList.remove("recording");
    }
  }
}

// Append Chat Message
function appendMessage(role, text) {
  if (!conversationContainer) return;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.innerText = text;
  conversationContainer.appendChild(bubble);
  conversationContainer.scrollTop = conversationContainer.scrollHeight;
}

// Play Spoken Audio Reply
function playAudioBase64(base64Data) {
  if (!base64Data) return;
  try {
    if (currentAudioPlayer) {
      currentAudioPlayer.pause();
    }
    const audioUrl = `data:audio/mp3;base64,${base64Data}`;
    currentAudioPlayer = new Audio(audioUrl);
    currentAudioPlayer.onended = () => {
      setStatus("Tap microphone or speak");
    };
    setStatus("Speaking...");
    currentAudioPlayer.play();
  } catch (err) {
    console.warn("Audio playback error:", err);
    setStatus("Tap microphone or speak");
  }
}

// Render Confirmation Box
function showConfirmation(promptText, toolName) {
  if (!confirmationContainer) return;
  confirmationContainer.innerHTML = `
    <div class="confirmation-card">
      <div class="confirmation-prompt">${promptText}</div>
      <div class="confirmation-actions">
        <button class="btn-confirm" onclick="sendVoiceText('Yes, please confirm and submit.')">Confirm</button>
        <button class="btn-cancel" onclick="sendVoiceText('Cancel this request.')">Cancel</button>
      </div>
    </div>
  `;
}

function clearConfirmation() {
  if (confirmationContainer) {
    confirmationContainer.innerHTML = "";
  }
}

// Send Audio Blob to Server
async function sendAudio(blob) {
  setStatus("Transcribing audio...");
  const formData = new FormData();
  formData.append("audio", blob, "recording.webm");

  try {
    const res = await fetch("/api/v1/voice/chat", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || `Server returned ${res.status}`);
    }

    handleAssistantResponse(data);
  } catch (err) {
    console.error("Chat error:", err);
    setStatus("Tap microphone to retry");
    appendMessage(
      "assistant",
      err.message.includes("quota") || err.message.includes("credits")
        ? "Speech recognition service quota exhausted. Please check your API key or click the quick prompt options below."
        : "Sorry, I had trouble processing your voice. Please try speaking again or click the prompts below."
    );
  }
}

// Send Text Message to Server
async function sendVoiceText(text) {
  setStatus("Thinking...");
  appendMessage("user", text);
  clearConfirmation();

  const formData = new FormData();
  formData.append("text", text);

  try {
    const res = await fetch("/api/v1/voice/chat", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || `Server returned ${res.status}`);
    }

    handleAssistantResponse(data, false);
  } catch (err) {
    console.error("Chat error:", err);
    setStatus("Tap microphone or speak");
    appendMessage("assistant", "Sorry, could not connect to server. Please try again.");
  }
}

// Process Response from Backend
function handleAssistantResponse(data, appendUser = true) {
  if (appendUser && data.transcript) {
    appendMessage("user", data.transcript);
  }

  appendMessage("assistant", data.reply_text);

  // If write confirmation needed
  if (data.pending_action) {
    showConfirmation(data.reply_text, data.pending_action.tool_name);
  } else {
    clearConfirmation();
  }

  // Play spoken audio if present
  if (data.audio_base64) {
    playAudioBase64(data.audio_base64);
  } else {
    setStatus("Tap microphone or speak");
  }
}

// Handle Auto-stop after silence is detected
async function handleAutoStop() {
  if (!isMicActive) return;
  console.log("Auto-stopping mic: speaking finished.");
  isMicActive = false;
  setStatus("Processing your voice...");
  try {
    const audioBlob = await recorder.stop();
    await sendAudio(audioBlob);
  } catch (err) {
    console.error("Auto-stop recording error:", err);
    setStatus("Tap microphone to speak");
  }
}

// Handle Mic Button Click (Toggle manual start/stop)
async function toggleRecording() {
  if (!isMicActive) {
    try {
      await recorder.start(handleAutoStop);
      isMicActive = true;
      setStatus("Listening... (auto-detects when you finish speaking)", true);
    } catch (err) {
      alert(err.message);
      setStatus("Microphone permission denied");
    }
  } else {
    setStatus("Processing voice...");
    isMicActive = false;
    try {
      const audioBlob = await recorder.stop();
      await sendAudio(audioBlob);
    } catch (err) {
      console.error("Recording stop error:", err);
      setStatus("Recording error. Try again.");
    }
  }
}

// Initialize Mic Listener
if (micBtn) {
  micBtn.addEventListener("click", toggleRecording);
}
