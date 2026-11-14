/**
 * KIT Real-Time Voice Assistant — Premium Client Application Controller
 * Handles Audio Recording, Live Waveform, Server AI Streaming, and Persona Switching.
 * NOTE: Strictly DOES NOT use browser Web Speech API (SpeechRecognition).
 */

const recorder = new window.AudioRecorder();
let isMicActive = false;
let currentAudioPlayer = null;

// DOM Elements
const micBtn = document.getElementById("mic-btn");
const statusText = document.getElementById("status-text");
const statusDot = document.getElementById("status-dot");
const conversationStream = document.getElementById("conversation-stream");
const confirmationContainer = document.getElementById("confirmation-container");
const waveCanvas = document.getElementById("voice-wave");
const textInput = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");

// Attach live waveform canvas to recorder if present
if (waveCanvas) {
  recorder.attachCanvas(waveCanvas);
}

// Update voice status indicator
function setStatus(text, state = "idle") {
  if (statusText) statusText.innerText = text;
  
  if (statusDot) {
    statusDot.className = "status-dot";
    if (state === "recording") statusDot.classList.add("recording");
    else if (state === "active" || state === "speaking") statusDot.classList.add("active");
  }

  if (micBtn) {
    if (state === "recording") {
      micBtn.classList.add("recording");
    } else {
      micBtn.classList.remove("recording");
    }
  }
}

// Format current time HH:MM
function getCurrentTimeStr() {
  const now = new Date();
  return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Append Chat Message Bubble to Stream
function appendMessage(role, text, audioBase64 = null) {
  if (!conversationStream) return;

  const row = document.createElement("div");
  row.className = `msg-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.innerText = role === "user" ? "YOU" : "KIT";

  const contentCol = document.createElement("div");
  contentCol.className = "msg-bubble-content";

  const header = document.createElement("div");
  header.className = "msg-header";
  header.innerText = role === "user" ? `You · ${getCurrentTimeStr()}` : `KIT Voice Assistant · ${getCurrentTimeStr()}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerText = text;

  contentCol.appendChild(header);
  contentCol.appendChild(bubble);

  // If assistant returned audio base64, attach a Listen Again replay button
  if (role === "assistant" && audioBase64) {
    const replayBtn = document.createElement("button");
    replayBtn.className = "msg-audio-replay";
    replayBtn.innerHTML = "<span>🔊</span> Listen Spoken Audio";
    replayBtn.onclick = () => playAudioBase64(audioBase64);
    contentCol.appendChild(replayBtn);
  }

  row.appendChild(avatar);
  row.appendChild(contentCol);

  conversationStream.appendChild(row);
  conversationStream.scrollTop = conversationStream.scrollHeight;
}

// Play Spoken Audio Reply via Web Audio / HTML5 Audio
function playAudioBase64(base64Data) {
  if (!base64Data) return;
  try {
    if (currentAudioPlayer) {
      currentAudioPlayer.pause();
    }
    const audioUrl = `data:audio/mp3;base64,${base64Data}`;
    currentAudioPlayer = new Audio(audioUrl);
    
    currentAudioPlayer.onplay = () => {
      setStatus("Speaking response...", "speaking");
    };

    currentAudioPlayer.onended = () => {
      setStatus("Tap microphone or speak", "idle");
    };

    currentAudioPlayer.onerror = (e) => {
      console.warn("Audio playback error:", e);
      setStatus("Tap microphone or speak", "idle");
    };

    currentAudioPlayer.play().catch(e => {
      console.warn("Audio autoplay blocked or cancelled:", e);
      setStatus("Tap microphone or speak", "idle");
    });
  } catch (err) {
    console.warn("Audio play exception:", err);
    setStatus("Tap microphone or speak", "idle");
  }
}

// Render Two-Step Confirmation Box for Write Actions
function showConfirmation(promptText, toolName) {
  if (!confirmationContainer) return;
  confirmationContainer.innerHTML = `
    <div class="confirmation-card">
      <div class="confirmation-prompt">⚠️ Action Confirmation Required:<br>${promptText}</div>
      <div class="confirmation-actions">
        <button class="btn-confirm-yes" onclick="sendVoiceText('Yes, confirm and proceed with submission.')">
          ✓ Yes, Confirm Action
        </button>
        <button class="btn-confirm-cancel" onclick="sendVoiceText('No, cancel this action.')">
          ✕ Cancel
        </button>
      </div>
    </div>
  `;
}

function clearConfirmation() {
  if (confirmationContainer) {
    confirmationContainer.innerHTML = "";
  }
}

// Send Audio Blob to Server (Web Speech API is NEVER used)
async function sendAudio(blob) {
  setStatus("Transcribing voice with Whisper...", "active");
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

    handleAssistantResponse(data, true);
  } catch (err) {
    console.error("Voice chat error:", err);
    setStatus("Tap microphone to retry", "idle");
    appendMessage(
      "assistant",
      "I had trouble hearing your audio. Please tap the microphone again or type your question below."
    );
  }
}

// Send Text Message to Voice Assistant
async function sendVoiceText(text) {
  if (!text || !text.trim()) return;
  const query = text.trim();

  // Clear text input if present
  if (textInput) textInput.value = "";

  setStatus("Analyzing query...", "active");
  appendMessage("user", query);
  clearConfirmation();

  const formData = new FormData();
  formData.append("text", query);

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
    console.error("Text chat error:", err);
    setStatus("Tap microphone or speak", "idle");
    appendMessage("assistant", "Could not reach server. Please check your connection and retry.");
  }
}

// Process Response from Backend
function handleAssistantResponse(data, appendUserTranscript = true) {
  if (appendUserTranscript && data.transcript) {
    appendMessage("user", data.transcript);
  }

  appendMessage("assistant", data.reply_text, data.audio_base64);

  // If write confirmation is required
  if (data.pending_action) {
    showConfirmation(data.reply_text, data.pending_action.tool_name);
  } else {
    clearConfirmation();
  }

  // Play spoken audio if present
  if (data.audio_base64) {
    playAudioBase64(data.audio_base64);
  } else {
    setStatus("Tap microphone or speak", "idle");
  }
}

// Auto-stop handler after silence detection
async function handleAutoStop() {
  if (!isMicActive) return;
  console.log("Auto-stopping mic: silence detected.");
  isMicActive = false;
  setStatus("Processing your voice...", "active");
  try {
    const audioBlob = await recorder.stop();
    await sendAudio(audioBlob);
  } catch (err) {
    console.error("Auto-stop error:", err);
    setStatus("Tap microphone to speak", "idle");
  }
}

// Mic Button Click Toggle
async function toggleRecording() {
  if (!isMicActive) {
    try {
      await recorder.start(handleAutoStop);
      isMicActive = true;
      setStatus("Listening... speak your query naturally", "recording");
    } catch (err) {
      alert("Microphone error: " + err.message);
      setStatus("Microphone permission denied", "idle");
    }
  } else {
    setStatus("Processing voice...", "active");
    isMicActive = false;
    try {
      const audioBlob = await recorder.stop();
      await sendAudio(audioBlob);
    } catch (err) {
      console.error("Recording stop error:", err);
      setStatus("Recording error. Please retry.", "idle");
    }
  }
}

// Hook up event listeners
if (micBtn) {
  micBtn.addEventListener("click", toggleRecording);
}

if (sendBtn && textInput) {
  sendBtn.addEventListener("click", () => sendVoiceText(textInput.value));
  textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      sendVoiceText(textInput.value);
    }
  });
}

// Unified Persona Switcher & Authentication Helpers
async function quickLoginAndRedirect(username) {
  try {
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login_id: username, password: "Kit@2026" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      window.location.href = "/portal";
    } else {
      alert("Login failed: " + (data.detail || "Invalid credentials"));
    }
  } catch (err) {
    alert("Login request error: " + err.message);
  }
}

async function doLogoutAndRedirect() {
  try {
    await fetch("/api/v1/auth/logout", { method: "POST" });
  } catch (e) {}
  window.location.href = "/";
}

// Highlight active persona in demo bar
async function syncActivePersonaBar() {
  try {
    const res = await fetch("/api/v1/auth/me");
    const data = await res.json();
    
    // Highlight button in demo switcher bar
    const pills = document.querySelectorAll(".switcher-btn");
    pills.forEach(p => p.classList.remove("active-persona"));

    if (data.authenticated) {
      const activeBtn = document.getElementById(`demo-${data.login_id}`);
      if (activeBtn) activeBtn.classList.add("active-persona");

      const headerUser = document.getElementById("header-user-badge");
      if (headerUser) {
        headerUser.style.display = "flex";
        headerUser.innerHTML = `<span class="dot-live"></span> ${data.full_name || data.login_id} (${data.role.toUpperCase()})`;
      }

      const loginBtn = document.getElementById("header-login-btn");
      if (loginBtn) {
        loginBtn.innerText = "Log Out";
        loginBtn.className = "btn-header-action btn-header-logout";
        loginBtn.onclick = (e) => { e.preventDefault(); doLogoutAndRedirect(); };
      }
    } else {
      const publicBtn = document.getElementById("demo-public");
      if (publicBtn) publicBtn.classList.add("active-persona");

      const loginBtn = document.getElementById("header-login-btn");
      if (loginBtn) {
        loginBtn.innerText = "Portal Login";
        loginBtn.className = "btn-header-action btn-header-login";
        loginBtn.onclick = () => { window.location.href = "/portal"; };
      }
    }
  } catch (err) {}
}

document.addEventListener("DOMContentLoaded", syncActivePersonaBar);
