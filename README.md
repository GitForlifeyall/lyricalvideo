# Node.js Project

A basic Node.js project configured with Express, ES Modules, environment variables support, and hot-reloading with Nodemon.

## 🚀 Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` (already done by default):
```bash
cp .env.example .env
```

### 3. Run the Application

- **Development Mode (with auto-reload):**
  ```bash
  npm run dev
  ```

- **Production Mode:**
  ```bash
  npm start
  ```

## 📦 Installed Dependencies
- [`express`](https://expressjs.com/) - Web framework
- [`dotenv`](https://github.com/motdotla/dotenv) - Environment variable management
- [`cors`](https://github.com/expressjs/cors) - Cross-Origin Resource Sharing middleware
- [`nodemon`](https://nodemon.io/) *(dev)* - Auto-restarts server on file changes

## 🛣️ Default Endpoints
- `GET /` - Root status & welcome message
- `GET /health` - Health check endpoint
