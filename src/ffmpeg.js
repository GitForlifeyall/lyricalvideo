import ffmpeg from 'fluent-ffmpeg';
import ffmpegInstaller from '@ffmpeg-installer/ffmpeg';
import ffprobeInstaller from '@ffprobe-installer/ffprobe';

// Automatically configure paths if system FFmpeg is not found
try {
  ffmpeg.setFfmpegPath(ffmpegInstaller.path);
  ffmpeg.setFfprobePath(ffprobeInstaller.path);
} catch (err) {
  console.warn('Using default system ffmpeg/ffprobe binary paths.');
}

export default ffmpeg;
