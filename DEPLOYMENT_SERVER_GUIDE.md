# Render Deployment Guide (FastAPI + Neon Postgres)

This guide explains how to deploy your DekhaHok application to **Render**.

## 1. Prerequisites
- Your code is already pushed to GitHub: `https://github.com/delower-sumon/DekhaHok.git`
- You have a **Neon** database.

## 2. Neon Database Credentials
You can use your existing Neon database. Here is your connection string (keep this secret!):

```env
DATABASE_URL=postgresql://neondb_owner:npg_OTt64FKohudr@ep-restless-leaf-a1byaugu-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

## 3. Deploying to Render

1.  Log in to [Render](https://render.com/).
2.  Click **New +** and select **Web Service**.
3.  Connect your GitHub repository: `delower-sumon/DekhaHok`.
4.  Configure the service:
    - **Name**: `dekhahok` (or any name)
    - **Runtime**: `Python 3`
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

5.  **Environment Variables**:
    Click the **Environment** tab on Render and add the following:
    - `DATABASE_URL`: `postgresql://neondb_owner:npg_OTt64FKohudr@ep-restless-leaf-a1byaugu-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`
    - `ADMIN_SECRET_KEY`: `Sumon@123` (or your preferred admin key)
    - `PYTHON_VERSION`: `3.11` (or your local version)

6.  Click **Create Web Service**.

## 4. Why Render is Better for this App
- **Postgres Support**: Render works perfectly with Neon and matching PostgreSQL drivers (`psycopg2`).
- **Automatic SSL**: Render provides HTTPS automatically.
- **Auto-Deploy**: Every time you push to GitHub, Render will automatically rebuild and update your site.

---
**Prepared by Antigravity AI**
