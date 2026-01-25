# GPU Acceleration Notes

## M1 GPU (MPS) Status

### Issue: Incomplete MPS Support in Coqui TTS

The Coqui TTS library uses PyTorch operations that are **not yet fully supported** on Apple Silicon (M1/M2) GPUs via MPS (Metal Performance Shaders).

**Specific Problem**:
- FFT operations (`aten::_fft_r2c`) are not implemented for MPS
- Moving model to MPS device causes synthesis to hang
- PyTorch suggests `PYTORCH_ENABLE_MPS_FALLBACK=1` but this doesn't fully solve the issue

### What We Tried

1. ✅ **Detected MPS availability**: `torch.backends.mps.is_available()` returns `True`
2. ✅ **Moved model to MPS**: `tts.to('mps')` - but this hangs during synthesis
3. ❌ **Enabled CPU fallback**: `PYTORCH_ENABLE_MPS_FALLBACK=1` - server hangs during model transfer
4. ❌ **GPU-accelerated synthesis**: Not possible with current TTS library + PyTorch version

### Current Solution: CPU (Fast & Stable)

**CPU performance is already very good**:
- First synthesis: ~23 seconds (server startup + model load + synthesis)
- Subsequent: ~6-10 seconds (model already loaded)
- This is **90% faster** than original 60 seconds

**Why CPU is acceptable**:
- XTTS-v2 is optimized for CPU inference
- M1 Pro CPU is very fast (10 cores)
- Server keeps model loaded (eliminates 40s model loading time)
- Quality is perfect (noise reduction restored)

## Quality Fix (More Important Than GPU!)

### The Real Problem

The crackly/static sound wasn't due to GPU vs CPU - it was because **noise reduction was missing** from the server implementation!

**What was lost**:
```python
# This gentle noise reduction was in the original synthesize_jarvis_ultimate.py
# but missing from jarvis_server.py
audio_clean = nr.reduce_noise(
    y=audio,
    sr=sr,
    stationary=True,
    prop_decrease=0.75,  # Gentle 75% reduction
)
```

### Solution

✅ **Added noise reduction back to server**:
- Imported `noisereduce` library
- Added `gentle_noise_removal()` method
- Applied in synthesis pipeline before clarity boost
- **Result**: Quality restored to original level

## Performance Comparison

| Scenario | Time | Notes |
|----------|------|-------|
| **Original (no server)** | ~60s | Loads model every time |
| **Server + CPU (first call)** | ~23s | Startup + model load |
| **Server + CPU (subsequent)** | ~6-10s | ⚡ Model already loaded |
| **GPU (attempted)** | N/A | Hangs/fails - not supported |

## Future GPU Acceleration

For GPU acceleration to work on M1, we would need:

1. **Wait for PyTorch MPS improvements**
   - FFT operations support
   - Better model transfer
   - Current PyTorch 2.1.0 has limited MPS support

2. **Or upgrade to newer TTS library**
   - When Coqui TTS or alternatives add proper MPS support
   - May require PyTorch 2.2+ with better MPS

3. **Or use ONNX Runtime**
   - Convert model to ONNX format
   - Use CoreML or Metal backend
   - Significant refactoring required

## Recommendation

**Keep current CPU implementation**:
- ✅ 6-10 second synthesis time is excellent
- ✅ Quality is perfect (noise reduction restored)
- ✅ Stable and reliable
- ✅ No GPU complexity

For faster synthesis (<1s), would need:
- Different model architecture (faster but lower quality)
- Pre-generated phrases (not dynamic)
- Or wait for better M1 GPU support in TTS libraries

**Current speed is great for conversational AI use!**
