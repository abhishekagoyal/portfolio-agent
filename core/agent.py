import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

def get_anthropic_client():
    try:
        import streamlit as st
        api_key = st.secrets.get('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    except Exception:
        api_key = os.getenv('ANTHROPIC_API_KEY')
    return anthropic.Anthropic(api_key=api_key)

def analyze_portfolio_risk(positions: list, span_results: dict) -> str:
    client = get_anthropic_client()
    positions_text = json.dumps(positions, indent=2)
    span_text = json.dumps(span_results, indent=2)
    prompt = 'You are a senior risk manager at a hedge fund. Analyze this portfolio and provide a concise risk narrative.' + chr(10) + chr(10) + 'POSITIONS:' + chr(10) + positions_text + chr(10) + chr(10) + 'SPAN MARGIN RESULTS:' + chr(10) + span_text + chr(10) + chr(10) + 'Provide:' + chr(10) + '1. Overall risk assessment (2-3 sentences)' + chr(10) + '2. Top 3 risk concentrations' + chr(10) + '3. Margin efficiency observations (spread credits helping?)' + chr(10) + '4. One actionable recommendation' + chr(10) + chr(10) + 'Be concise and professional. Use numbers where relevant.'
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1024,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return message.content[0].text

def map_news_to_positions(positions: list, news_headlines: list) -> str:
    client = get_anthropic_client()
    positions_text = json.dumps([p.get('symbol') for p in positions])
    headlines_text = chr(10).join('- ' + h for h in news_headlines)
    prompt = 'You are a portfolio manager. Map these news headlines to portfolio positions and identify impact.' + chr(10) + chr(10) + 'PORTFOLIO SYMBOLS: ' + positions_text + chr(10) + chr(10) + 'NEWS HEADLINES:' + chr(10) + headlines_text + chr(10) + chr(10) + 'For each relevant headline: 1. Which position(s) does it affect? 2. Directional impact (bullish/bearish/neutral)? 3. Urgency (high/medium/low)? Format as a clean bullet list.'
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1024,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return message.content[0].text

def suggest_trades(positions: list, span_results: dict) -> str:
    client = get_anthropic_client()
    positions_text = json.dumps(positions, indent=2)
    margin_req = span_results.get('net_margin_requirement', 0)
    spread_credits = span_results.get('total_spread_credits', 0)
    prompt = 'You are a derivatives strategist. Suggest trades to optimize this portfolio.' + chr(10) + chr(10) + 'CURRENT POSITIONS:' + chr(10) + positions_text + chr(10) + chr(10) + 'MARGIN SUMMARY:' + chr(10) + '- Net margin requirement: $' + str(margin_req) + chr(10) + '- Spread credits earned: $' + str(spread_credits) + chr(10) + chr(10) + 'Suggest top 3 trades that would: 1. Reduce margin requirement OR 2. Improve risk/reward OR 3. Add useful hedges. For each: action, instrument, rationale, expected margin impact.'
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1024,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return message.content[0].text

def ask_portfolio_question(positions: list, span_results: dict, question: str) -> str:
    client = get_anthropic_client()
    positions_text = json.dumps(positions, indent=2)
    span_text = json.dumps(span_results, indent=2)
    prompt = 'You are a portfolio risk assistant. Answer this question about the portfolio.' + chr(10) + chr(10) + 'POSITIONS:' + chr(10) + positions_text + chr(10) + chr(10) + 'SPAN RESULTS:' + chr(10) + span_text + chr(10) + chr(10) + 'QUESTION: ' + question + chr(10) + chr(10) + 'Answer concisely and professionally. Use specific numbers from the portfolio data.'
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=512,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return message.content[0].text