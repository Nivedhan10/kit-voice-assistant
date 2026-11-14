/**
 * Pure Audio Recording Engine with:
 * 1. Web Audio API AnalyserNode for live voice waveform visualization.
 * 2. Automatic Voice Activity / Silence Detection (auto-stops when speaking stops).
 * NOTE: Strictly DOES NOT use browser Web Speech API (SpeechRecognition).
 */

class AudioRecorder {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.stream = null;
    this.isRecording = false;

    // Web Audio API for waveform and VAD
    this.audioCtx = null;
    this.analyser = null;
    this.source = null;
    this.animFrameId = null;

    // Silence detection parameters
    this.silenceThreshold = 12; // Sound volume threshold
    this.silenceTimeoutMs = 1800; // Auto-stop after 1.8s of silence
    this.silenceTimer = null;
    this.hasSpoken = false;
    this.onAutoStop = null;
    this.canvas = null;
    this.canvasCtx = null;
  }

  attachCanvas(canvasElement) {
    this.canvas = canvasElement;
    if (this.canvas) {
      this.canvasCtx = this.canvas.getContext("2d");
    }
  }

  async start(onAutoStopCallback = null) {
    if (this.isRecording) return;
    this.onAutoStop = onAutoStopCallback;

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
      });

      // Mime type selection
      const mimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/mp4",
        "",
      ];
      let selectedMime = "";
      for (const mime of mimeTypes) {
        if (!mime || MediaRecorder.isTypeSupported(mime)) {
          selectedMime = mime;
          break;
        }
      }

      const options = selectedMime ? { mimeType: selectedMime } : {};
      this.mediaRecorder = new MediaRecorder(this.stream, options);
      this.audioChunks = [];

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      // Initialize Web Audio API for live waveform & silence detection
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AudioContextClass();
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 256;
      this.source = this.audioCtx.createMediaStreamSource(this.stream);
      this.source.connect(this.analyser);

      this.hasSpoken = false;
      this.isRecording = true;
      this.mediaRecorder.start(250);

      // Start drawing live waveform and monitoring volume
      this._startVisualizerAndVAD();

    } catch (err) {
      console.error("Microphone access error:", err);
      throw new Error("Could not access microphone. Please grant permission.");
    }
  }

  _startVisualizerAndVAD() {
    if (!this.analyser) return;

    const bufferLength = this.analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      if (!this.isRecording) return;

      this.analyser.getByteFrequencyData(dataArray);

      // Calculate average audio level (Volume RMS)
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i];
      }
      const avgVolume = sum / bufferLength;

      // Draw live waveform on canvas if attached
      if (this.canvas && this.canvasCtx) {
        const width = this.canvas.width;
        const height = this.canvas.height;

        this.canvasCtx.clearRect(0, 0, width, height);

        // Draw frequency bars
        const barWidth = (width / bufferLength) * 2.5;
        let barHeight;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
          barHeight = (dataArray[i] / 255) * height * 0.9;

          // Gradient color: blue to active violet
          this.canvasCtx.fillStyle = avgVolume > this.silenceThreshold
            ? `rgb(37, 99, ${Math.min(255, 150 + dataArray[i])})`
            : "rgba(148, 163, 184, 0.4)";

          this.canvasCtx.fillRect(x, height / 2 - barHeight / 2, barWidth, barHeight);
          x += barWidth + 1;
        }
      }

      // Voice Activity & Silence Detection (Auto-stop)
      if (avgVolume > this.silenceThreshold) {
        this.hasSpoken = true;
        // User is currently speaking; clear any pending silence timeout
        if (this.silenceTimer) {
          clearTimeout(this.silenceTimer);
          this.silenceTimer = null;
        }
      } else if (this.hasSpoken) {
        // User had started speaking, but has now gone silent
        if (!this.silenceTimer) {
          this.silenceTimer = setTimeout(() => {
            console.log("Auto-stopping recording: Silence detected after speech.");
            if (this.isRecording && this.onAutoStop) {
              this.onAutoStop();
            }
          }, this.silenceTimeoutMs);
        }
      }

      this.animFrameId = requestAnimationFrame(draw);
    };

    draw();
  }

  stop() {
    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder || !this.isRecording) {
        return reject(new Error("Recorder not active."));
      }

      if (this.silenceTimer) {
        clearTimeout(this.silenceTimer);
        this.silenceTimer = null;
      }
      if (this.animFrameId) {
        cancelAnimationFrame(this.animFrameId);
        this.animFrameId = null;
      }

      this.mediaRecorder.onstop = () => {
        const mimeType = this.mediaRecorder.mimeType || "audio/webm";
        const audioBlob = new Blob(this.audioChunks, { type: mimeType });

        // Close audio context and tracks
        if (this.stream) {
          this.stream.getTracks().forEach((track) => track.stop());
          this.stream = null;
        }
        if (this.audioCtx && this.audioCtx.state !== "closed") {
          this.audioCtx.close().catch(() => {});
          this.audioCtx = null;
        }

        // Clear canvas
        if (this.canvas && this.canvasCtx) {
          this.canvasCtx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }

        this.isRecording = false;
        resolve(audioBlob);
      };

      this.mediaRecorder.stop();
    });
  }
}

window.AudioRecorder = AudioRecorder;
