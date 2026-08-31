import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const LYRICS_DIR = path.join(__dirname, '../lyrics');

// Ensure lyrics directory exists
if (!fs.existsSync(LYRICS_DIR)) {
  fs.mkdirSync(LYRICS_DIR, { recursive: true });
}

const app = express();
const PORT = process.env.PORT || 3000;

const USER_AGENT = 'LyricalVideo/1.0 (https://github.com/GitForlifeyall/lyricalvideo)';

// In-memory store for currently active/selected song lyrics and timestamps
let currentSongSession = null;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static frontend assets
app.use(express.static(path.join(__dirname, '../public')));

/**
 * Utility: Parse raw LRC text into structured timestamps JSON
 * @param {string} lrcText 
 * @returns {Array<{index: number, timestamp: string, timeSeconds: number, timeMs: number, text: string}>}
 */
export function parseLrcTimestamps(lrcText) {
  if (!lrcText || typeof lrcText !== 'string') return [];
  
  const lines = lrcText.split('\n');
  const result = [];
  const timeRegex = /\[(\d{2}):(\d{2})(?:\.(\d{2,3}))?\](.*)/;

  let idx = 0;
  for (const line of lines) {
    const match = line.match(timeRegex);
    if (match) {
      const minutes = parseInt(match[1], 10);
      const seconds = parseInt(match[2], 10);
      const millis = match[3] ? (match[3].length === 2 ? parseInt(match[3], 10) * 10 : parseInt(match[3], 10)) : 0;
      const totalSeconds = parseFloat((minutes * 60 + seconds + millis / 1000).toFixed(3));
      const totalMs = minutes * 60000 + seconds * 1000 + millis;
      const text = match[4].trim();

      if (text.length > 0) {
        result.push({
          index: idx++,
          timestamp: `${match[1]}:${match[2]}${match[3] ? '.' + match[3] : ''}`,
          timeSeconds: totalSeconds,
          timeMs: totalMs,
          text: text,
        });
      }
    }
  }

  return result;
}

// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', uptime: process.uptime() });
});

/**
 * GET /api/lyrics/synced
 * Search and return song metadata, raw synced LRC text, and parsed JSON timestamps
 */
app.get('/api/lyrics/synced', async (req, res) => {
  try {
    const { q, track_name, artist_name, album_name } = req.query;

    let targetUrl;
    if (q) {
      targetUrl = `https://lrclib.net/api/search?q=${encodeURIComponent(q)}`;
    } else if (track_name) {
      const params = new URLSearchParams();
      params.append('track_name', track_name);
      if (artist_name) params.append('artist_name', artist_name);
      if (album_name) params.append('album_name', album_name);
      targetUrl = `https://lrclib.net/api/search?${params.toString()}`;
    } else {
      return res.status(400).json({ error: 'Search parameter "q" or "track_name" is required' });
    }

    const response = await fetch(targetUrl, {
      headers: { 'User-Agent': USER_AGENT },
    });

    if (!response.ok) {
      const errorText = await response.text();
      return res.status(response.status).json({ error: 'LRCLIB API error', details: errorText });
    }

    const searchResults = await response.json();
    if (!Array.isArray(searchResults) || searchResults.length === 0) {
      return res.status(404).json({ error: 'No songs found matching query', query: q || track_name });
    }

    // Pick best match (prefer one with syncedLyrics)
    const bestMatch = searchResults.find(item => !!(item.syncedLyrics && item.syncedLyrics.trim().length > 0)) || searchResults[0];
    const parsedLines = parseLrcTimestamps(bestMatch.syncedLyrics || '');

    const resultPayload = {
      id: bestMatch.id,
      trackName: bestMatch.trackName || bestMatch.name,
      artistName: bestMatch.artistName,
      albumName: bestMatch.albumName,
      duration: bestMatch.duration,
      instrumental: bestMatch.instrumental || false,
      hasSyncedLyrics: !!bestMatch.syncedLyrics,
      rawLrc: bestMatch.syncedLyrics || null,
      plainLyrics: bestMatch.plainLyrics || null,
      syncedLines: parsedLines,
      totalLines: parsedLines.length,
      allMatchesCount: searchResults.length
    };

    // Save as current active session
    currentSongSession = resultPayload;

    return res.json(resultPayload);
  } catch (error) {
    console.error('Error fetching synced lyrics:', error);
    return res.status(500).json({ error: 'Failed to process synced lyrics', message: error.message });
  }
});

/**
 * GET /api/lyrics/search
 * Standard LRCLIB search endpoint with raw results list
 */
app.get('/api/lyrics/search', async (req, res) => {
  try {
    const { q, track_name, artist_name, album_name } = req.query;

    let targetUrl;
    if (q) {
      targetUrl = `https://lrclib.net/api/search?q=${encodeURIComponent(q)}`;
    } else if (track_name) {
      const params = new URLSearchParams();
      params.append('track_name', track_name);
      if (artist_name) params.append('artist_name', artist_name);
      if (album_name) params.append('album_name', album_name);
      targetUrl = `https://lrclib.net/api/search?${params.toString()}`;
    } else {
      return res.status(400).json({ error: 'Search query "q" or "track_name" is required' });
    }

    const response = await fetch(targetUrl, {
      headers: { 'User-Agent': USER_AGENT },
    });

    if (!response.ok) {
      const errorText = await response.text();
      return res.status(response.status).json({ error: 'LRCLIB API error', details: errorText });
    }

    const data = await response.json();
    
    // Attach parsed syncedLines and sort tracks with synced lyrics first
    const formattedData = Array.isArray(data) ? data
      .map(item => ({
        ...item,
        syncedLines: parseLrcTimestamps(item.syncedLyrics || ''),
        hasSyncedLyrics: !!(item.syncedLyrics && item.syncedLyrics.trim().length > 0)
      }))
      .sort((a, b) => (b.hasSyncedLyrics === a.hasSyncedLyrics ? 0 : b.hasSyncedLyrics ? 1 : -1))
      : data;

    return res.json(formattedData);
  } catch (error) {
    console.error('Error searching lyrics:', error);
    return res.status(500).json({ error: 'Failed to search lyrics', message: error.message });
  }
});

/**
 * POST /api/lyrics/save
 * Save the synchronized JSON time-synced file to the backend's `lyrics/` folder
 */
app.post('/api/lyrics/save', async (req, res) => {
  try {
    const { track, customFilename } = req.body;
    if (!track) {
      return res.status(400).json({ error: 'Track payload is required' });
    }

    await fs.promises.mkdir(LYRICS_DIR, { recursive: true });

    const safeArtist = (track.artistName || 'Unknown_Artist').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
    const safeTitle = (track.trackName || track.name || 'Unknown_Track').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
    
    const filename = customFilename 
      ? `${customFilename.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`
      : `${safeArtist}_${safeTitle}.json`;

    const filePath = path.join(LYRICS_DIR, filename);

    const parsedLines = track.syncedLines && track.syncedLines.length > 0
      ? track.syncedLines
      : parseLrcTimestamps(track.syncedLyrics || '');

    const payloadToSave = {
      id: track.id,
      trackName: track.trackName || track.name,
      artistName: track.artistName,
      albumName: track.albumName,
      duration: track.duration,
      instrumental: track.instrumental || false,
      hasSyncedLyrics: !!(track.syncedLyrics || (parsedLines && parsedLines.length > 0)),
      savedAt: new Date().toISOString(),
      totalLines: parsedLines.length,
      syncedLines: parsedLines,
      rawLrc: track.syncedLyrics || null,
      plainLyrics: track.plainLyrics || null
    };

    await fs.promises.writeFile(filePath, JSON.stringify(payloadToSave, null, 2), 'utf-8');

    // Also write companion .lrc file if synced lyrics exist
    if (track.syncedLyrics) {
      const lrcFilename = filename.replace(/\.json$/, '.lrc');
      const lrcFilePath = path.join(LYRICS_DIR, lrcFilename);
      await fs.promises.writeFile(lrcFilePath, track.syncedLyrics, 'utf-8');
    }

    return res.json({
      status: 'success',
      message: `Successfully saved synced JSON to lyrics folder!`,
      filename: filename,
      filePath: `lyrics/${filename}`,
      totalLines: parsedLines.length,
      savedData: payloadToSave
    });
  } catch (error) {
    console.error('Error saving lyrics file:', error);
    return res.status(500).json({ error: 'Failed to save lyrics file', message: error.message });
  }
});

/**
 * GET /api/lyrics/saved
 * List all saved lyric files in the `lyrics/` directory
 */
app.get('/api/lyrics/saved', async (req, res) => {
  try {
    if (!fs.existsSync(LYRICS_DIR)) {
      return res.json({ files: [] });
    }

    const fileList = await fs.promises.readdir(LYRICS_DIR);
    const jsonFiles = fileList.filter(f => f.endsWith('.json'));

    const results = await Promise.all(
      jsonFiles.map(async (filename) => {
        try {
          const content = await fs.promises.readFile(path.join(LYRICS_DIR, filename), 'utf-8');
          const parsed = JSON.parse(content);
          return {
            filename,
            trackName: parsed.trackName,
            artistName: parsed.artistName,
            totalLines: parsed.totalLines || (parsed.syncedLines ? parsed.syncedLines.length : 0),
            savedAt: parsed.savedAt,
            hasSyncedLyrics: parsed.hasSyncedLyrics
          };
        } catch {
          return { filename };
        }
      })
    );

    return res.json({ total: results.length, files: results });
  } catch (error) {
    console.error('Error listing saved lyrics:', error);
    return res.status(500).json({ error: 'Failed to list saved files' });
  }
});

/**
 * POST /api/lyrics/parse-lrc
 * Parse arbitrary LRC text passed in request body into JSON timestamps
 */
app.post('/api/lyrics/parse-lrc', (req, res) => {
  const { lrc } = req.body;
  if (typeof lrc !== 'string') {
    return res.status(400).json({ error: 'Field "lrc" (string) is required' });
  }

  const lines = parseLrcTimestamps(lrc);
  return res.json({
    totalLines: lines.length,
    lines: lines
  });
});

/**
 * POST /api/lyrics/select
 * Save or register the active track and its timestamps in backend state
 */
app.post('/api/lyrics/select', (req, res) => {
  const { track } = req.body;
  if (!track) {
    return res.status(400).json({ error: 'Track object is required' });
  }

  const parsedLines = parseLrcTimestamps(track.syncedLyrics || '');
  currentSongSession = {
    ...track,
    rawLrc: track.syncedLyrics || null,
    syncedLines: parsedLines,
    totalLines: parsedLines.length,
    updatedAt: new Date().toISOString()
  };

  return res.json({
    status: 'success',
    message: 'Active song session updated',
    session: currentSongSession
  });
});

/**
 * GET /api/lyrics/current
 * Retrieve the active song session and timestamps from backend
 */
app.get('/api/lyrics/current', (req, res) => {
  if (!currentSongSession) {
    return res.status(404).json({ error: 'No active song session selected yet' });
  }
  return res.json(currentSongSession);
});

// Start server
app.listen(PORT, () => {
  console.log(`🎵 LyricalVideo Server is running on http://localhost:${PORT}`);
});
