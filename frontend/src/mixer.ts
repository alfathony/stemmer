import { encodeWav } from "./wav";

export interface Track {
  name: string;
  buffer: AudioBuffer;
  gain: GainNode;
  volume: number;
  muted: boolean;
  solo: boolean;
  source?: AudioBufferSourceNode;
}

/**
 * Plays every stem through its own GainNode. All sources are started at the
 * same AudioContext time, which keeps them sample-locked.
 */
export class Mixer {
  readonly ctx = new AudioContext();
  readonly master = this.ctx.createGain();
  readonly tracks: Track[] = [];
  playing = false;
  onEnded?: () => void;

  private offset = 0;     // position (s) when paused
  private startedAt = 0;  // ctx time that corresponds to position 0

  constructor() {
    this.master.connect(this.ctx.destination);
  }

  get duration(): number {
    return Math.max(0, ...this.tracks.map((t) => t.buffer.duration));
  }

  get currentTime(): number {
    const t = this.playing ? this.ctx.currentTime - this.startedAt : this.offset;
    return Math.min(Math.max(t, 0), this.duration);
  }

  addTrack(name: string, buffer: AudioBuffer): Track {
    const gain = this.ctx.createGain();
    gain.connect(this.master);
    const track: Track = { name, buffer, gain, volume: 1, muted: false, solo: false };
    this.tracks.push(track);
    return track;
  }

  /** Gain a track should have right now, given mute/solo across all tracks. */
  effectiveGain(track: Track): number {
    const anySolo = this.tracks.some((t) => t.solo);
    if (track.muted || (anySolo && !track.solo)) return 0;
    return track.volume;
  }

  updateGains(): void {
    for (const t of this.tracks) {
      // Short ramp avoids clicks when dragging sliders.
      t.gain.gain.setTargetAtTime(this.effectiveGain(t), this.ctx.currentTime, 0.015);
    }
  }

  async play(): Promise<void> {
    if (this.playing) return;
    await this.ctx.resume();
    if (this.offset >= this.duration) this.offset = 0;
    const when = this.ctx.currentTime + 0.05;
    for (const t of this.tracks) {
      const src = this.ctx.createBufferSource();
      src.buffer = t.buffer;
      src.connect(t.gain);
      src.start(when, this.offset);
      t.source = src;
    }
    // The longest buffer decides when playback is over.
    const longest = this.tracks.reduce((a, b) => (b.buffer.duration > a.buffer.duration ? b : a));
    longest.source!.onended = () => {
      if (!this.playing) return;
      this.stopSources();
      this.playing = false;
      this.offset = this.duration;
      this.onEnded?.();
    };
    this.startedAt = when - this.offset;
    this.playing = true;
    this.updateGains();
  }

  pause(): void {
    if (!this.playing) return;
    this.offset = this.currentTime;
    this.playing = false;
    this.stopSources();
  }

  seek(seconds: number): void {
    const wasPlaying = this.playing;
    this.pause();
    this.offset = Math.min(Math.max(seconds, 0), this.duration);
    if (wasPlaying) void this.play();
  }

  /** Render the current mix (volumes, mutes, solos) offline to a WAV blob. */
  exportMix(): Promise<Blob> {
    return this.render(this.tracks.map((t) => [t, this.effectiveGain(t)]));
  }

  /** One stem on its own at its slider volume; mute and solo are ignored. */
  exportTrack(track: Track): Promise<Blob> {
    return this.render([[track, track.volume]]);
  }

  private async render(levels: [Track, number][]): Promise<Blob> {
    const rate = this.tracks[0].buffer.sampleRate;
    const offline = new OfflineAudioContext(2, Math.ceil(this.duration * rate), rate);
    for (const [t, level] of levels) {
      if (level === 0) continue;
      const src = offline.createBufferSource();
      src.buffer = t.buffer;
      const g = offline.createGain();
      g.gain.value = level;
      src.connect(g).connect(offline.destination);
      src.start(0);
    }
    return encodeWav(await offline.startRendering());
  }

  async close(): Promise<void> {
    this.pause();
    await this.ctx.close();
  }

  private stopSources(): void {
    for (const t of this.tracks) {
      if (!t.source) continue;
      t.source.onended = null;
      t.source.stop();
      t.source.disconnect();
      t.source = undefined;
    }
  }
}
