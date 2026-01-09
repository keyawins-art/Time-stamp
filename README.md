# 🕐 Session Tracker & Logger

A premium web dashboard and client-side logger for tracking device runtimes and sessions.

## ✨ Features
- **Modern Dashboard**: Real-time overview of all devices.
- **Bar Graph History**: Historical daily runtime visualization starting from Jan 1st, 2026.
- **Daily CSV Logging**: Automatically saves starting and ending times to `logs/sessions_YYYY-MM-DD.csv`.
- **Lightweight Client**: Simple Python script to track device uptime.

## 🚀 Local Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Server**:
   ```bash
   python app.py
   ```
   Access the dashboard at `http://localhost:5000`.

3. **Run the Client**:
   ```bash
   python client.py
   ```
   *Note: Edit `DEVICE_ID` in `client.py` to identify your device.*

## ☁️ Deployment

### GitHub & Render
1. Push this code to a **GitHub repository**.
2. Connect the repository to **[Render](https://render.com/)**.
3. Render will automatically detect `render.yaml` and:
   - Setup a **PostgreSQL Database**.
   - Deploy the **Flask Web Service**.
4. **Environment Variables**:
   - `DATABASE_URL`: Automatically provided by Render.
   - `PYTHON_VERSION`: Set to `3.11.0`.

## 📁 Project Structure
- `app.py`: Flask backend with SQL / CSV logging logic.
- `client.py`: The tracker script to run on your devices.
- `templates/`: HTML5 dashboard layouts.
- `static/`: Assets like logos.
- `logs/`: (Auto-created) Daily CSV session logs.
