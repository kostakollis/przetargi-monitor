"""Monitor przetargów foto/wideo - 3 platformy"""
import os
import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright
import httpx

# Frazy do wyszukiwania
SEARCH_PHRASES = [
    "fotografia", "fotograf", "zdjęcia", "zdjęcie",
    "film", "film promocyjny", "film korporacyjny", "film reklamowy",
    "film instruktażowy", "film szkoleniowy", "reportaż filmowy",
    "produkcja filmowa", "produkcja wideo", "realizacja filmów",
    "realizacja wideo", "filmowanie", "spot reklamowy",
    "spot promocyjny", "operator kamery", "operator drona",
    "sesja zdjęciowa", "sesja fotograficzna", "wideo",
    "dokumentacja fotograficzna", "dokumentacja filmowa",
    "materiały promocyjne", "materiały wideo",
    "fotografia lotnicza", "animacja", "postprodukcja",
    "kamerzysta", "fotograf eventowy",
]

# Słowa kluczowe — co MUSI być w tytule oferty żeby pasowała
KEYWORDS = [
    "fotograf", "fotograficzn", "zdjęć", "zdjęci", "zdjęcia",
    "film promocyjn", "film korporacyjn", "film reklamow",
    "film instruktażow", "film szkolen", "filmu", "filmów",
    "filmow", "filmowan", "produkcja film", "realizacja film",
    "produkcja wideo", "realiza
