# Trademark Monitor

**In-House USPTO Trademark Monitoring System for Relatent, Inc.**

Monitor USPTO trademark filings for potential conflicts with TOPO and TOPOLOGY marks.

---

## Overview

This system monitors the USPTO's weekly trademark publications and daily filings for marks that could be confusingly similar to Relatent's trademarks:

- **TOPO** (Serial No. 99/634122, 99/634130) - Classes 9 & 42
- **TOPOLOGY** (Serial No. 99/634140, 99/634135) - Classes 9 & 42

### Key Features

- ✅ **Automated Monitoring** - Downloads and parses USPTO daily XML files
- ✅ **Smart Similarity Detection** - Multiple algorithms (Levenshtein, Soundex, pattern matching)
- ✅ **Class-Based Filtering** - Only flags marks in relevant classes (9, 42)
- ✅ **Keyword Analysis** - Prioritizes software/tech/social networking goods/services
- ✅ **Email & Slack Alerts** - Get notified immediately when conflicts are found
- ✅ **Web Dashboard** - View, manage, and track conflicts
- ✅ **Historical Tracking** - Database of all processed filings

---

## Quick Start

### 1. Installation

```bash
# Clone or extract the project
cd trademark_monitor

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings (email, Slack webhook, etc.)
nano .env
```

### 3. Run Your First Scan

```bash
# Test with sample data first
python run_monitor.py --sample --days 7

# Run actual scan (downloads USPTO data)
python run_monitor.py --days 7
```

### 4. Launch Dashboard

```bash
python run_monitor.py --dashboard
# Open http://localhost:8501
```

---

## Usage

### Command Line Interface

```bash
# Run monitoring scan (last 7 days)
python run_monitor.py

# Scan specific number of days
python run_monitor.py --days 30

# Test with sample data (no USPTO download)
python run_monitor.py --sample

# Launch web dashboard
python run_monitor.py --dashboard

# Check status of our trademark applications
python run_monitor.py --check-status

# Run as scheduled service (daily at 8 AM)
python run_monitor.py --schedule

# Show help
python run_monitor.py --help
```

### Web Dashboard

The Streamlit dashboard provides:

1. **Dashboard** - Overview of monitoring status and recent conflicts
2. **Conflicts** - Detailed view of all flagged marks with actions
3. **Our Trademarks** - Status of Relatent's trademark applications
4. **Run Monitor** - Trigger manual scans
5. **Settings** - Configure alerts and test notifications

---

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SMTP_SERVER` | SMTP server for email alerts | For email |
| `SMTP_USERNAME` | SMTP username | For email |
| `SMTP_PASSWORD` | SMTP password/app password | For email |
| `ALERT_FROM_EMAIL` | Sender email address | For email |
| `ALERT_TO_EMAIL` | Recipient email address | For email |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL | For Slack |
| `USPTO_API_KEY` | USPTO TSDR API key (optional) | No |

### Config File (config/config.yaml)

The YAML configuration file allows detailed customization:

```yaml
# Your trademarks to monitor
trademarks:
  - name: "TOPO"
    serial_numbers: ["99634122", "99634130"]
    classes: [9, 42]
  - name: "TOPOLOGY"
    serial_numbers: ["99634140", "99634135"]
    classes: [9, 42]

# Classes to monitor for conflicts
monitored_classes: [9, 42]

# Keywords that increase concern
high_priority_keywords:
  - software
  - mobile
  - social
  - networking
  - app

# Similarity settings
similarity:
  min_score: 65  # Minimum score to flag (0-100)
```

---

## How It Works

### 1. Data Collection

The system downloads USPTO's Trademark Daily XML (TDXF) files, which contain all trademark applications filed each day. These files are publicly available at no cost from the USPTO's bulk data portal.

### 2. Parsing

XML files are parsed to extract:
- Mark text (word mark)
- Serial number
- Filing date
- International classes
- Goods/services description
- Applicant information

### 3. Filtering

Only marks in relevant classes are analyzed:
- **Class 9**: Downloadable software, mobile apps
- **Class 42**: Online software services, social networking

### 4. Similarity Analysis

Multiple algorithms detect potential conflicts:

| Method | Description | Weight |
|--------|-------------|--------|
| Exact Match | Identical marks | 100% |
| Prefix Match | Starts with TOPO/TOPOLOGY | 85% |
| Contains | Contains our mark | 70% |
| Levenshtein | Edit distance similarity | Variable |
| Phonetic | Soundex/Metaphone matching | 75% |
| Pattern | Regex patterns (TOPO*, etc.) | 75% |

### 5. Scoring

Final score combines:
- Mark similarity (70% weight)
- Class/keyword relevance (30% weight)

Marks scoring ≥65% are flagged for review.

### 6. Alerting

When conflicts are found:
- **Email**: HTML-formatted report with details and TSDR links
- **Slack**: Interactive message with action buttons

---

## Deployment

### Option 1: Local/Server with Cron

```bash
# Edit crontab
crontab -e

# Add daily run at 8 AM
0 8 * * * cd /path/to/trademark_monitor && /path/to/venv/bin/python run_monitor.py >> logs/cron.log 2>&1
```

### Option 2: Docker

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# Run monitoring
CMD ["python", "run_monitor.py", "--schedule"]
```

### Option 3: Cloud Platforms

**Railway/Render:**
1. Push code to GitHub
2. Connect repository to Railway/Render
3. Set environment variables in dashboard
4. Deploy with start command: `python run_monitor.py --schedule`

**AWS/GCP/Azure:**
- Use Cloud Functions/Lambda for scheduled execution
- Store database in cloud storage (S3, GCS, etc.)

---

## Understanding Alerts

### Similarity Scores

| Score | Severity | Action |
|-------|----------|--------|
| 85-100% | 🔴 High | Immediate review, likely opposition candidate |
| 75-84% | 🟠 Medium | Review soon, assess confusion risk |
| 65-74% | 🟡 Low | Monitor, lower priority |

### Recommended Workflow

1. **Review** flagged marks in the dashboard
2. **Assess** actual likelihood of confusion:
   - How similar are the goods/services?
   - Is the applicant in our industry?
   - Same geographic market?
3. **Decide** on action:
   - **Dismiss** if not a real concern
   - **Mark Reviewed** if watching but not acting
   - **Action Taken** if filing opposition or sending cease & desist

### Opposition Timeline

If a concerning mark is found:
- **30 days** from publication to file Notice of Opposition
- Can request 90-day extension (up to 180 days total)
- Consult with IP counsel (Orrick) for opposition filings

---

## Data Sources

### Primary: USPTO Daily XML (TDXF)

- **URL**: https://bulkdata.uspto.gov/data/trademark/dailyxml/applications
- **Format**: ZIP files containing XML
- **Update Frequency**: Daily (weekdays)
- **Cost**: Free

### Secondary: TSDR API

- **URL**: https://tsdrapi.uspto.gov/ts/cd
- **Use**: Detailed trademark lookups
- **Rate Limit**: 60 requests/minute
- **Cost**: Free (requires API key registration)

---

## Troubleshooting

### Common Issues

**"No files downloaded"**
- USPTO may not publish on weekends/holidays
- Check your internet connection
- Try a longer lookback period

**"Email not sending"**
- For Gmail: Use App Passwords, not regular password
- Check SMTP settings in .env
- Ensure less secure app access or app password is configured

**"Slack webhook failed"**
- Verify webhook URL is correct
- Check Slack workspace permissions
- Test with curl: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test"}' YOUR_WEBHOOK_URL`

**"High memory usage"**
- USPTO XML files can be large
- Increase system RAM or process files in batches
- Use the `--days` flag to limit scope

### Logs

Check `logs/trademark_monitor.log` for detailed error messages.

---

## Cost Comparison

| Solution | Annual Cost |
|----------|-------------|
| Law firm watch service | $4,000/year |
| **This system** | **$0** (your time + hosting) |

Potential hosting costs:
- **Free**: Railway/Render free tier, local server
- **Low cost**: $5-20/month for VPS

---

## Support & Maintenance

### Updating Our Trademarks

If new trademarks are filed, update `config/config.yaml`:

```yaml
trademarks:
  - name: "NEW_MARK"
    serial_numbers: ["99999999"]
    classes: [9, 42]
```

### Adding Watch Patterns

Add custom regex patterns in the config:

```yaml
similarity:
  watch_patterns:
    - "^NEWPATTERN"
    - "PATTERN$"
```

### Database Backup

```bash
# Backup
cp data/trademark_monitor.db data/backup_$(date +%Y%m%d).db

# The database is SQLite - easy to inspect with any SQLite tool
```

---

## Legal Notes

This system is designed for **monitoring purposes only**. It:
- Does NOT provide legal advice
- Does NOT file oppositions automatically
- Is NOT a substitute for professional IP counsel

For actual opposition filings or legal action, consult with your trademark attorney (Orrick).

---

## License

Internal use only - Relatent, Inc.

---

## Contact

For technical issues with this system, contact your engineering team.
For trademark legal questions, contact Orrick law firm.
