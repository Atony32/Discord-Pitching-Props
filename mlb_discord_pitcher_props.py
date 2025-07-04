# 📦 Install required packages
!pip install requests pandas --quiet

# 📚 Import libraries
import requests
import pandas as pd
from datetime import datetime
import time
import os
import json

# 📡 Discord webhook URL (set your actual webhook here)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# 🔑 API key and base URL
MLB_API_BASE = 'https://statsapi.mlb.com/api/v1'

# ⚾ Reference Ranges for Analysis
REFERENCE = {
    'Confidence Score': {
        'Strong Bet': '≥ 0.6',
        'Consider': '0.3 – 0.59',
        'Avoid/Fade': '< 0.3'
    }
}

# 🔍 Get today's pitchers
def get_today_pitchers():
    today = datetime.today().strftime('%Y-%m-%d')
    url = f"{MLB_API_BASE}/schedule?sportId=1&date={today}&hydrate=team,linescore,probablePitcher"
    res = requests.get(url)
    data = res.json()
    games = data.get('dates', [])
    if not games:
        return []

    pitchers = []
    for game in games[0]['games']:
        for side in ['away', 'home']:
            try:
                pitcher = game['teams'][side]['probablePitcher']
                team = game['teams'][side]['team']['name']
                opponent = game['teams']['home' if side == 'away' else 'away']['team']['name']
                pitchers.append({'id': pitcher['id'], 'team': team, 'opponent': opponent})
            except:
                continue
    return pitchers

# 🧠 Get pitcher stats
def get_pitcher_stats(pitcher_id):
    url = f"{MLB_API_BASE}/people/{pitcher_id}/stats?stats=season&group=pitching"
    res = requests.get(url)
    data = res.json()
    stats_array = data.get('stats', [])
    if not stats_array:
        return None
    stats = stats_array[0].get('splits', [])
    if not stats:
        return None

    season_data = stats[0]['stat']
    name = stats[0]['player']['fullName']
    return {
        'Name': name,
        'ERA': float(season_data.get('era', 0)),
        'WHIP': float(season_data.get('whip', 0)),
        'Strikeouts': int(season_data.get('strikeOuts', 0)),
        'Walks': int(season_data.get('baseOnBalls', 0)),
        'Games Started': int(season_data.get('gamesStarted', 1)),
        'Hits': int(season_data.get('hits', 0)),
        'Innings Pitched': float(season_data.get('inningsPitched', 1))
    }

# ➕ Score props
def score_props(stats):
    avg_k_per_start = 6.0
    avg_hits_per_ip = 1.1
    avg_era = 4.0
    avg_whip = 1.25
    avg_outs_per_game = 18

    scores = {}

    k_score = (stats['K/Start'] - avg_k_per_start) / avg_k_per_start
    scores['Over Strikeouts'] = max(k_score, 0)
    scores['Under Strikeouts'] = max(-k_score, 0)

    hits_score = (stats['Hits/IP'] - avg_hits_per_ip) / avg_hits_per_ip
    scores['Over Hits Allowed'] = max(hits_score, 0)
    scores['Under Hits Allowed'] = max(-hits_score, 0)

    era_score = (avg_era - stats['ERA']) / avg_era
    whip_score = (avg_whip - stats['WHIP']) / avg_whip
    er_score = (era_score + whip_score) / 2
    scores['Under Earned Runs'] = max(er_score, 0)
    scores['Over Earned Runs'] = max(-er_score, 0)

    outs_score = (stats['Outs/Game'] - avg_outs_per_game) / avg_outs_per_game
    scores['Over Pitching Outs'] = max(outs_score, 0)
    scores['Under Pitching Outs'] = max(-outs_score, 0)

    best_prop = max(scores, key=scores.get)
    confidence = scores[best_prop]

    return best_prop, confidence

# 📝 Rating helpers
def rate_era(era):
    if era < 2.50:
        return "Excellent"
    elif era < 3.50:
        return "Good"
    elif era < 4.50:
        return "Average"
    else:
        return "Poor"

def rate_whip(whip):
    if whip < 1.00:
        return "Excellent"
    elif whip < 1.20:
        return "Good"
    elif whip < 1.35:
        return "Average"
    else:
        return "Poor"

def rate_k_per_9(k9):
    if k9 >= 10:
        return "Elite Strikeout Pitcher"
    elif k9 >= 8:
        return "Good Strikeout Pitcher"
    elif k9 >= 6:
        return "Average Strikeout Rate"
    else:
        return "Low Strikeout Rate"

def rate_bb_per_9(bb9):
    if bb9 < 2.0:
        return "Excellent Control"
    elif bb9 < 3.0:
        return "Above Average Control"
    elif bb9 < 4.0:
        return "Average Control"
    else:
        return "Wild / Poor Control"

# 💡 Fade suggestion
def get_fade_suggestion(best_prop, grade):
    if grade == 'Avoid':
        if "Over" in best_prop:
            return "Bet Under " + best_prop.replace("Over ", "")
        elif "Under" in best_prop:
            return "Bet Over " + best_prop.replace("Under ", "")
    return ""

# 📤 Send message to Discord
def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        return
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(data), headers={"Content-Type": "application/json"})
    except:
        print("❌ Failed to send to Discord.")

# 🧠 Analyze all pitchers
def analyze_pitchers():
    pitchers = get_today_pitchers()
    if not pitchers:
        print("❌ No usable pitcher data found today.")
        return pd.DataFrame()

    data = []
    for p in pitchers:
        stats = get_pitcher_stats(p['id'])
        if not stats:
            continue
        stats['Team'] = p['team']
        stats['Opponent'] = p['opponent']
        try:
            stats['K/Start'] = round(stats['Strikeouts'] / stats['Games Started'], 2)
            stats['Hits/IP'] = round(stats['Hits'] / stats['Innings Pitched'], 2)
            stats['BB/Game'] = round(stats['Walks'] / stats['Games Started'], 2)
            stats['Outs/Game'] = round(stats['Innings Pitched'] * 3 / stats['Games Started'], 1)
            stats['K/9'] = round(stats['Strikeouts'] * 9 / stats['Innings Pitched'], 2)
            stats['BB/9'] = round(stats['Walks'] * 9 / stats['Innings Pitched'], 2)
        except ZeroDivisionError:
            stats['K/Start'] = stats['Hits/IP'] = stats['BB/Game'] = stats['Outs/Game'] = stats['K/9'] = stats['BB/9'] = 0

        best_prop, confidence = score_props(stats)
        stats['Best Prop'] = best_prop
        stats['Confidence Score'] = round(confidence, 3)

        if confidence >= 0.6:
            grade = 'Strong Bet'
        elif confidence >= 0.3:
            grade = 'Consider'
        else:
            grade = 'Avoid'

        stats['Bet Grade'] = grade
        stats['Fade'] = 'Yes' if grade == 'Avoid' else ('Optional' if grade == 'Consider' else 'No')
        stats['Fade Suggestion'] = get_fade_suggestion(best_prop, grade)
        stats['Track Bet'] = ''

        stats['ERA Rating'] = rate_era(stats['ERA'])
        stats['WHIP Rating'] = rate_whip(stats['WHIP'])
        stats['K/9 Rating'] = rate_k_per_9(stats['K/9'])
        stats['BB/9 Rating'] = rate_bb_per_9(stats['BB/9'])

        data.append(stats)
        time.sleep(0.3)

    return pd.DataFrame(data)

# ▶️ Run and print
if __name__ == "__main__":
    df = analyze_pitchers()
    pd.set_option('display.max_rows', None)

    if not df.empty:
        today_str = datetime.today().strftime('%Y-%m-%d')
        print("\n📘 Confidence Score Ranges:")
        for k, v in REFERENCE['Confidence Score'].items():
            print(f"- {k}: {v}")

        display_cols = ['Name', 'Team', 'Opponent', 'K/Start', 'Hits/IP', 'ERA', 'ERA Rating',
                        'WHIP', 'WHIP Rating', 'K/9', 'K/9 Rating', 'BB/9', 'BB/9 Rating',
                        'BB/Game', 'Outs/Game', 'Best Prop', 'Confidence Score',
                        'Bet Grade', 'Fade', 'Fade Suggestion', 'Track Bet']

        print(f"\n✅ Ant's Nova Picks for {today_str}")
        display(df[display_cols].sort_values(by='Confidence Score', ascending=False))

        # 📨 Send top 5 picks to Discord
        top_df = df.sort_values(by='Confidence Score', ascending=False).head(5)
        message_lines = [f"🔥 **Top 5 Pitcher Props for {today_str}**"]
        for _, row in top_df.iterrows():
            message_lines.append(
                f"- **{row['Name']} ({row['Team']} vs {row['Opponent']})**\n  ➤ {row['Best Prop']} (Confidence: {row['Confidence Score']}, Grade: {row['Bet Grade']})"
            )
        send_to_discord("\n".join(message_lines))
