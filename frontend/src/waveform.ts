/** Peak amplitude per column, across all channels, normalised to 0..1. */
export function computePeaks(buffer: AudioBuffer, columns: number): Float32Array {
  const peaks = new Float32Array(columns);
  const step = buffer.length / columns;
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const data = buffer.getChannelData(c);
    for (let col = 0; col < columns; col++) {
      const start = Math.floor(col * step);
      const end = Math.min(Math.floor((col + 1) * step), data.length);
      let max = peaks[col];
      // Stride through long windows; exact peaks don't matter visually.
      const stride = Math.max(1, Math.floor((end - start) / 400));
      for (let i = start; i < end; i += stride) {
        const v = Math.abs(data[i]);
        if (v > max) max = v;
      }
      peaks[col] = max;
    }
  }
  const top = Math.max(...peaks, 1e-6);
  return peaks.map((p) => p / top);
}

export function drawWaveform(
  canvas: HTMLCanvasElement,
  peaks: Float32Array,
  color: string,
): void {
  const dpr = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const g = canvas.getContext("2d")!;
  g.scale(dpr, dpr);
  g.clearRect(0, 0, width, height);
  const mid = height / 2;

  // Faint centre line, then 2 px bars with 1 px gaps (each bar = loudest peak in its span).
  g.fillStyle = color;
  g.globalAlpha = 0.35;
  g.fillRect(0, mid - 0.5, width, 1);
  g.globalAlpha = 1;
  const bar = 2;
  const pitch = 3;
  const bars = Math.max(1, Math.floor(width / pitch));
  for (let b = 0; b < bars; b++) {
    const from = Math.floor((b / bars) * peaks.length);
    const to = Math.max(from + 1, Math.floor(((b + 1) / bars) * peaks.length));
    let p = 0;
    for (let i = from; i < to; i++) if (peaks[i] > p) p = peaks[i];
    const h = Math.max(1, p * (height * 0.4));
    g.fillRect(b * pitch, mid - h, bar, h * 2);
  }
}
