import os
import re
import time
import requests
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

def get_nike_price(url):
    options = uc.ChromeOptions()
    options.headless = False
    
    display = None
    if os.name == 'posix':
        from pyvirtualdisplay import Display
        display = Display(visible=0, size=(1024, 768))
        display.start()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=145)
        driver.get(url)
        time.sleep(15) # Wait for page to fully load and Akamai to pass
        html = driver.page_source
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for the price. Nike usually uses spans or divs with the price formatted as R$ 1.234,56
        price_texts = soup.find_all(string=re.compile(r'R\$\s*\d+'))
        prices = []
        for text in price_texts:
            match = re.search(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text)
            if match:
                price_str = match.group(1).replace('.', '').replace(',', '.')
                prices.append(float(price_str))
                
        if prices:
            # We assume the lowest valid price found is the current price (in case of discounts)
            # Sometimes parsing pulls other irrelevant R$ numbers, let's filter those realistically > 50
            valid_prices = [p for p in prices if p > 50]
            if valid_prices:
                return min(valid_prices)
            
        print("Price not found in HTML. Check if Akamai blocked the request.")
        return None
    except Exception as e:
        print(f"Error occurred: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        if display:
            display.stop()

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

def main():
    url = "https://www.nike.com.br/tenis-nike-precision-7-masculino-028985.html?cor=5A"
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("Warning: Telegram configuration missing. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    
    price = get_nike_price(url)
    
    if price is not None:
        print(f"Current price found: R$ {price:.2f}")
        # Always send a message for testing purposes if it's the first run, or condition it:
        # We will strictly follow the rule: < 300 
        if price <= 300.00:
            message = f"🚨 <b>Preço Baixou!</b> 🚨\n\nO Tênis Nike Precision 7 Masculino está custando <b>R$ {price:.2f}</b>!\n\nLink: {url}"
            if bot_token and chat_id:
                send_telegram_message(bot_token, chat_id, message)
            else:
                print("Would have sent message, but no Telegram credentials found.")
        else:
            print(f"Price is R$ {price:.2f}, which is above R$ 300.00. No notification sent.")
            
            # For demonstration during testing, if we run locally and want to ensure the bot works:
            if os.getenv("TEST_MODE") == "1" and bot_token and chat_id:
                msg = f"🧪 <b>Teste do Robô</b>\n\nO robô está funcionando! Preço atual lido: R$ {price:.2f}"
                send_telegram_message(bot_token, chat_id, msg)

    else:
        print("Failed to retrieve the price.")

if __name__ == "__main__":
    main()
