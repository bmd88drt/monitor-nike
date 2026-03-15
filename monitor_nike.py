import os
import re
import time
import requests
from bs4 import BeautifulSoup

def get_nike_price(url):
    api_key = os.getenv("SCRAPINGANT_API_KEY")
    if not api_key:
        print("Error: SCRAPINGANT_API_KEY environment variable not set.")
        return None, None

    # Payload explicitly asks ScrapingAnt to use a browser and residential proxy in Brazil
    payload = {
        'url': url,
        'x-api-key': api_key,
        'browser': 'true',
        'proxy_type': 'residential',
        'proxy_country': 'br'
    }

    try:
        print("Sending request via ScrapingAnt API...")
        response = requests.get('https://api.scrapingant.com/v2/general', params=payload, timeout=60)
        
        if response.status_code != 200:
            print(f"ScrapingAnt failed with status code: {response.status_code}\n{response.text}")
            return None, None

        html = response.text

        soup = BeautifulSoup(html, 'html.parser')
        
        # O preço do PIX costuma ter a string "no Pix" logo depois, ou "Pix" na tag filha.
        # Vamos procurar todo texto com R$. Nota: o site usa \xa0 (non-breaking space) entre R$ e os números.
        pix_price = None
        installments_text = None

        # Procura textos que tenham R$ seguido de espaços comuns ou non-breaking e números
        text_nodes = soup.find_all(string=re.compile(r'R\$\s*\xa0*\s*\d+'))
        
        for text in text_nodes:
            # Pega o texto do elemento inteiro (do pai) ou do pai do pai para garantir que "Pix" seja capturado se estiver em tag adjacente
            parent_text = text
            if text.parent and text.parent.parent:
                parent_text = text.parent.parent.text
            elif text.parent:
                parent_text = text.parent.text
                
            parent_lower = parent_text.lower()
            
            # Tenta achar valor do Pix
            if 'pix' in parent_lower:
                match = re.search(r'R\$\s*\xa0*\s*(\d{1,3}(?:\.\d{3})*,\d{2})', parent_text)
                if match:
                    price_str = match.group(1).replace('.', '').replace(',', '.')
                    pix_price = float(price_str)
                    
            # Tenta achar valor de parcela (ex: "ou 4x de R$ 112,50 sem juros")
            if 'sem juros' in parent_lower and 'x' in parent_lower:
                match = re.search(r'(?:ou\s*)?(\d+x\s*de\s*R\$\s*\xa0*\s*\d{1,3}(?:\.\d{3})*,\d{2}\s*sem\s*juros)', parent_lower, re.IGNORECASE)
                if match:
                    installments_text = match.group(1).strip().capitalize()
                    # Normalizar espaços
                    installments_text = re.sub(r'\s+', ' ', installments_text).replace('\xa0', ' ')
                else:
                    installments_text = parent_text.strip().replace('\xa0', ' ')
                
        # Fallback: Se não achou algo com Pix explicitamente, mas achou outras coisas:
        if pix_price is None:
            prices = []
            for text in text_nodes:
                match = re.search(r'R\$\s*\xa0*\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text)
                if match:
                    price_str = match.group(1).replace('.', '').replace(',', '.')
                    val = float(price_str)
                    if val > 50 and val < 3000: # Remove valores absurdos ou de parcelas isoladas
                        prices.append(val)
            if prices:
                # Ordenar
                prices.sort(reverse=True)
                # O segundo maior valor costuma ser o de venda (o primeiro é o original riscado)
                if len(prices) >= 2:
                    pix_price = prices[1]
                elif len(prices) == 1:
                    pix_price = prices[0]

        if pix_price:
            return pix_price, installments_text
            
        print("Price not found in HTML. Check if Akamai blocked the request.")
        return None, None
    except requests.exceptions.Timeout:
        print("Request to ScrapingAnt timed out.")
        return None, None
    except Exception as e:
        print(f"Error occurred: {e}")
        return None, None

def send_telegram_message(bot_token, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Notification sent successfully")
    else:
        print(f"Failed to send notification: {response.text}")

import json
from datetime import datetime, timezone, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- (O código das bibliotecas originais permanece no topo do arquivo. Vamos adicionar as novas de google no começo do arquivo logo)

def add_to_google_sheets(creds_json, price):
    try:
        # Define escopos para a API
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Carrega credenciais do JSON string
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
        # Autoriza o cliente
        client = gspread.authorize(creds)
        
        # Abre a planilha pelo nome exato (o usuário precisa ter criado uma planilha chamada "Preço Nike")
        # Mas para evitar erro caso o nome seja outro, vamos instruir a colocar por ID futuramente.
        # Por hora, vamos prever que o nome deve ser "Preco Nike" ou "Preço Nike"
        try:
            sheet = client.open("Preço Nike").sheet1
        except gspread.exceptions.SpreadsheetNotFound:
            try:
                sheet = client.open("Preco Nike").sheet1
            except gspread.exceptions.SpreadsheetNotFound:
                print("Spreadsheet 'Preço Nike' not found. Please create it and share it with the service account email.")
                return False

        # Prepara os dados (Data/Hora em Brasília e o Preço)
        brt_timezone = timezone(timedelta(hours=-3))
        now_brt = datetime.now(brt_timezone)
        date_str = now_brt.strftime("%d/%m/%Y")
        time_str = now_brt.strftime("%H:%M:%S")
        
        # Adiciona a linha (Data, Hora, Preço)
        sheet.append_row([date_str, time_str, f"R$ {price:.2f}"])
        print("Price successfully logged to Google Sheets.")
        return True
    except Exception as e:
        print(f"Failed to log to Google Sheets: {e}")
        return False

def main():
    url = "https://www.nike.com.br/tenis-nike-precision-7-masculino-028985.html?cor=5A"
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    google_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
    
    if not bot_token or not chat_id:
        print("Warning: Telegram configuration missing. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    
    result = get_nike_price(url)
    
    if result and result != (None, None):
        price, installments_text = result
        print(f"Current price found: R$ {price:.2f}")
        if installments_text:
            print(f"Installments info: {installments_text}")
            
        # 1. Log to Google Sheets
        if google_creds:
            add_to_google_sheets(google_creds, price)
        else:
            print("Warning: GOOGLE_CREDENTIALS_JSON not found. Skipping Google Sheets logging.")

        # 2. Telegram Notification Logic (Only at 12:00 BRT -> 15:00 UTC)
        # We need to check the current UTC hour. The cron action runs at 11, 15, and 23 UTC.
        current_utc_hour = datetime.utcnow().hour
        
        # Test mode should always send
        is_test_mode = os.getenv("TEST_MODE") == "1"
        
        # Telegram alert condition: test mode OR (it's around 15 UTC, which is 12 BRT)
        # We allow a small window (14 to 16) in case the runner is delayed.
        should_send_telegram = is_test_mode or (14 <= current_utc_hour <= 16)
        
        if should_send_telegram:
            # Envia a notificação, com destaque se for menor que 300
            if price and price <= 300.00:
                message = f"🚨 <b>ALERTA DE PREÇO BAIXO!</b> 🚨\n\nO Tênis Nike Precision 7 Masculino bateu a sua meta e está por <b>R$ {price:.2f} no Pix!</b>\n\n"
            else:
                message = f"👟 <b>Atualização Diária de Preço (12:00)</b>\n\nO tênis Nike Precision 7 Masculino está custando:\n<b>R$ {price:.2f} no Pix!</b>\n\n"
                
            if installments_text:
                message += f"💳 Parcelamento: <i>{installments_text}</i>\n\n"
                
            message += f"🛒 Link: {url}"
            
            if bot_token and chat_id:
                send_telegram_message(bot_token, chat_id, message)
            else:
                print("Would have sent message, but no Telegram credentials found.")
        else:
            print(f"Not sending Telegram notification. Current UTC hour is {current_utc_hour}. Notifications are only scheduled for 15:00 UTC (12:00 BRT).")

    else:
        print("Failed to retrieve the price.")

if __name__ == "__main__":
    main()
