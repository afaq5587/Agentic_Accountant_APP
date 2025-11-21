# Vercel Deployment Guide

## Prerequisites
1.  **Vercel CLI**: Ensure you have the Vercel CLI installed (`npm install -g vercel`).
2.  **Environment Variables**: You must set the following environment variables in your Vercel Project Settings:
    *   `GEMINI_API_KEY`: Your Google Gemini API key.
    *   `TAVILY_API_KEY`: Your Tavily API key (for web search).
    *   `SGA_DB_PATH`: `/tmp/members.db` (Recommended for serverless stability, though the code now defaults to this if needed).

## Deployment Steps
1.  **Deploy**:
    Run the following command in your terminal:
    ```bash
    vercel --prod
    ```

## Important Limitations
*   **Data Persistence**: Vercel functions are ephemeral. The SQLite database (`members.db`) and uploaded files are stored in `/tmp`, which **will be wiped** when the function restarts or redeploys.
*   **Production Use**: For a real production app, you must switch to a cloud database (like Vercel Postgres or MongoDB) and cloud storage (like AWS S3 or Vercel Blob).
