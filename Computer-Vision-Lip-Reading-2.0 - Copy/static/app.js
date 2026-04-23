// ─── DOM Elements ───
const statusBadge = document.getElementById('recording-status');
const statusIcon = statusBadge.querySelector('.icon');
const statusText = statusBadge.querySelector('.text');

const recordBtn = document.getElementById('record-btn');
const recordBtnText = recordBtn.querySelector('.record-btn-text');
const recordBtnIcon = recordBtn.querySelector('.record-btn-icon');
const timerDisplay = document.getElementById('timer-display');
const frameCount = document.getElementById('frame-count');
const recordTimer = document.getElementById('record-timer');

const currentWordEl = document.getElementById('current-word');
const currentConfidenceEl = document.getElementById('current-confidence');
const transcriptEl = document.getElementById('transcript');
const clearBtn = document.getElementById('clear-btn');
const processingBox = document.getElementById('processing-box');

// Mode toggle elements
const modeLiveBtn = document.getElementById('mode-live');
const modeSampleBtn = document.getElementById('mode-sample');
const livePanel = document.getElementById('live-panel');
const samplePanel = document.getElementById('sample-panel');
const liveControls = document.getElementById('live-controls');
const sampleControls = document.getElementById('sample-controls');

// Sample video elements
const sampleClipGrid = document.getElementById('sample-clip-grid');
const sampleVideoPlayer = document.getElementById('sample-video-player');
const samplePlaceholder = document.getElementById('sample-placeholder');
const sampleInferBtn = document.getElementById('sample-infer-btn');
const sampleSelectedName = document.getElementById('sample-selected-name');
const videoUploadInput = document.getElementById('video-upload');

let lastPredictionTimestamp = 0;
let isRecording = false;
let recordingStartTime = null;
let timerInterval = null;
let currentMode = 'live'; // 'live' or 'sample'
let selectedSampleFile = null;
let selectedSampleSource = 'sample'; // 'sample' or 'upload'


// ─── Mode Toggle ───

modeLiveBtn.addEventListener('click', () => switchMode('live'));
modeSampleBtn.addEventListener('click', () => switchMode('sample'));

function switchMode(mode) {
    currentMode = mode;
    
    // Update toggle buttons
    modeLiveBtn.classList.toggle('active', mode === 'live');
    modeSampleBtn.classList.toggle('active', mode === 'sample');
    
    // Show/hide panels
    livePanel.style.display = mode === 'live' ? '' : 'none';
    samplePanel.style.display = mode === 'sample' ? '' : 'none';
    liveControls.style.display = mode === 'live' ? '' : 'none';
    sampleControls.style.display = mode === 'sample' ? '' : 'none';
    
    // Load sample clips when switching to sample mode
    if (mode === 'sample') {
        loadSampleClips();
    }
}


// ─── Recording Control (Live Mode) ───

recordBtn.addEventListener('click', async () => {
    if (isRecording) {
        // STOP recording
        isRecording = false;
        recordBtn.classList.remove('recording');
        recordBtnIcon.textContent = '🎙️';
        recordBtnText.textContent = 'Start Recording';
        
        // Stop timer
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
        
        // Tell backend to stop recording and run inference
        const response = await fetch('/stop_recording');
        const data = await response.json();
        
        if (data.status === 'too_short') {
            currentWordEl.textContent = '⚠️ TOO SHORT';
            currentConfidenceEl.textContent = 'Please speak for at least 0.5 seconds';
        }
    } else {
        // START recording
        isRecording = true;
        recordBtn.classList.add('recording');
        recordBtnIcon.textContent = '⏹️';
        recordBtnText.textContent = 'Stop Recording';
        recordingStartTime = Date.now();
        
        // Start live timer
        timerInterval = setInterval(() => {
            const elapsed = ((Date.now() - recordingStartTime) / 1000).toFixed(1);
            timerDisplay.textContent = elapsed + 's';
        }, 100);
        
        // Tell backend to start recording
        await fetch('/start_recording');
    }
});


// ─── Sample Video Functions ───

async function loadSampleClips() {
    try {
        const response = await fetch('/sample_videos');
        const data = await response.json();
        
        if (data.clips.length === 0) {
            sampleClipGrid.innerHTML = `
                <div class="sample-empty">
                    <span class="sample-empty-icon">📭</span>
                    <p>No sample videos found.</p>
                    <p class="sample-empty-hint">Run <code>python download_samples.py</code> to download TED talk sample clips,<br>or upload your own video below.</p>
                </div>
            `;
            return;
        }
        
        sampleClipGrid.innerHTML = '';
        data.clips.forEach(clip => {
            const card = document.createElement('div');
            card.className = 'sample-clip-card';
            card.dataset.filename = clip.filename;
            card.innerHTML = `
                <div class="clip-icon">🎞️</div>
                <div class="clip-info">
                    <span class="clip-name">${clip.name}</span>
                    <span class="clip-desc">${clip.description}</span>
                    ${clip.duration ? `<span class="clip-duration">${clip.duration}s</span>` : ''}
                </div>
            `;
            card.addEventListener('click', () => selectSampleClip(clip.filename, clip.name, 'sample'));
            sampleClipGrid.appendChild(card);
        });
    } catch (err) {
        sampleClipGrid.innerHTML = '<div class="sample-loading">Error loading clips</div>';
        console.error('Error loading sample clips:', err);
    }
}

function selectSampleClip(filename, name, source) {
    selectedSampleFile = filename;
    selectedSampleSource = source;
    
    // Update video player
    const videoUrl = source === 'upload' ? `/uploaded_video/${filename}` : `/sample_video/${filename}`;
    sampleVideoPlayer.src = videoUrl;
    sampleVideoPlayer.style.display = 'block';
    samplePlaceholder.style.display = 'none';
    sampleVideoPlayer.load();
    
    // Update UI
    sampleInferBtn.disabled = false;
    sampleSelectedName.textContent = `Selected: ${name}`;
    
    // Highlight selected card
    document.querySelectorAll('.sample-clip-card').forEach(c => c.classList.remove('selected'));
    const card = document.querySelector(`.sample-clip-card[data-filename="${filename}"]`);
    if (card) card.classList.add('selected');
}

sampleInferBtn.addEventListener('click', async () => {
    if (!selectedSampleFile) return;
    
    sampleInferBtn.disabled = true;
    sampleInferBtn.querySelector('.record-btn-text').textContent = 'Processing...';
    processingBox.style.display = 'flex';
    
    try {
        const response = await fetch('/run_sample_inference', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: selectedSampleFile,
                source: selectedSampleSource,
            }),
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            currentWordEl.textContent = data.text.toUpperCase();
            currentConfidenceEl.textContent = `Sample video: ${data.filename}`;
            
            // Animate
            currentWordEl.style.animation = 'none';
            void currentWordEl.offsetWidth;
            currentWordEl.style.animation = 'fadeInSlideUp 0.4s ease forwards';
            
            appendToTranscript(data.text);
        } else {
            currentWordEl.textContent = '⚠️ ERROR';
            currentConfidenceEl.textContent = data.message || 'Inference failed';
        }
    } catch (err) {
        currentWordEl.textContent = '⚠️ ERROR';
        currentConfidenceEl.textContent = 'Network error';
        console.error('Inference error:', err);
    } finally {
        sampleInferBtn.disabled = false;
        sampleInferBtn.querySelector('.record-btn-text').textContent = 'Run Inference';
        processingBox.style.display = 'none';
    }
});


// ─── File Upload ───

videoUploadInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('video', file);
    
    sampleSelectedName.textContent = `Uploading ${file.name}...`;
    
    try {
        const response = await fetch('/upload_video', {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            selectSampleClip(data.filename, file.name, 'upload');
        } else {
            sampleSelectedName.textContent = `Error: ${data.message}`;
        }
    } catch (err) {
        sampleSelectedName.textContent = 'Upload failed';
        console.error('Upload error:', err);
    }
    
    // Reset file input
    videoUploadInput.value = '';
});


// ─── Transcript ───

function appendToTranscript(text) {
    const placeholder = transcriptEl.querySelector('.placeholder');
    if (placeholder) placeholder.remove();
    
    const span = document.createElement('span');
    span.className = 'transcript-word';
    span.textContent = text + ' ';
    transcriptEl.appendChild(span);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
}


// ─── Status Polling ───

async function fetchStatus() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        
        // Update header badge
        if (data.recording) {
            statusBadge.className = 'status-badge recording';
            statusIcon.textContent = '🔴';
            statusText.textContent = `Recording (${data.recorded_seconds}s)`;
            frameCount.textContent = `${data.recorded_frames} frames`;
        } else if (data.processing) {
            statusBadge.className = 'status-badge processing';
            statusIcon.textContent = '⏳';
            statusText.textContent = 'Processing...';
        } else {
            statusBadge.className = 'status-badge';
            statusIcon.textContent = '⚪';
            statusText.textContent = 'Ready';
        }
        
        // Show/hide processing indicator (only for live mode polling)
        if (currentMode === 'live') {
            processingBox.style.display = data.processing ? 'flex' : 'none';
        }
        
        // Update Prediction (sentence-level) — from live mode
        if (data.prediction && data.prediction.timestamp !== lastPredictionTimestamp) {
            // Only auto-update from live predictions
            if (!data.prediction.source || data.prediction.source !== 'sample_video' || currentMode === 'live') {
                lastPredictionTimestamp = data.prediction.timestamp;
                
                const predictedText = data.prediction.text;
                const duration = data.prediction.duration || '?';
                const numFrames = data.prediction.num_frames || '?';
                
                // Show in main display
                currentWordEl.textContent = predictedText.toUpperCase();
                currentConfidenceEl.textContent = `${duration}s recording • ${numFrames} frames analyzed`;
                
                // Animate
                currentWordEl.style.animation = 'none';
                void currentWordEl.offsetWidth;
                currentWordEl.style.animation = 'fadeInSlideUp 0.4s ease forwards';
                
                if (currentMode === 'live') {
                    appendToTranscript(predictedText);
                }
            }
        }
        
    } catch (err) {
        console.error("Error fetching status:", err);
    }
}

clearBtn.addEventListener('click', async () => {
    transcriptEl.innerHTML = '<span class="placeholder">Press Start, speak clearly while facing the camera, then press Stop. Predictions appear here.</span>';
    currentWordEl.innerHTML = '...';
    currentConfidenceEl.innerHTML = 'Waiting for speech';
    await fetch('/reset');
});

// Poll every 200ms
setInterval(fetchStatus, 200);
