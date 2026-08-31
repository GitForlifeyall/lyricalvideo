import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

const USER_AGENT = 'LyricalVideo/1.0 (https://github.com/GitForlifeyall/lyricalvideo)';

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static frontend assets
app.use(express.static(path.join(__dirname, '../public')));

// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', uptime: process.uptime() });
});

// LRCLIB Proxy: Search lyrics by query or track/artist
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
      headers: {
        'User-Agent': USER_AGENT,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      return res.status(response.status).json({ error: 'LRCLIB API error', details: errorText });
    }

    const data = await response.json();
    return res.json(data);
  } catch (error) {
    console.error('Error fetching lyrics from LRCLIB:', error);
    return res.status(500).json({ error: 'Failed to fetch lyrics', message: error.message });
  }
});

// LRCLIB Proxy: Get lyrics by ID
app.get('/api/lyrics/get/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const targetUrl = `https://lrclib.net/api/get/${encodeURIComponent(id)}`;

    const response = await fetch(targetUrl, {
      headers: {
        'User-Agent': USER_AGENT,
      },
    });

    if (!response.ok) {
      return res.status(response.status).json({ error: 'Failed to retrieve lyrics item' });
    }

    const data = await response.json();
    return res.json(data);
  } catch (error) {
    console.error('Error fetching single lyric:', error);
    return res.status(500).json({ error: 'Failed to fetch lyric details', message: error.message });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`🎵 LyricalVideo Server is running on http://localhost:${PORT}`);
});
