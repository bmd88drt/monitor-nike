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
        # Pega a versão 145 fixada para evitar o erro do Chrome 145 / Driver 146 no GitHub
        driver = uc.Chrome(options=options, version_main=145)
        driver.get(url)
        time.sleep(15) # Wait for page to fully load and Akamai to pass
        html = driver.page_source
        
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
    except Exception as e:
        print(f"Error occurred: {e}")
        return None, None
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
    
    result = get_nike_price(url)
    
    if result != (None, None):
        price, installments_text = result
        print(f"Current price found: R$ {price:.2f}")
        if installments_text:
            print(f"Installments info: {installments_text}")
            
        # Envia sempre a notificação, com destaque se for menor que 300
        if price <= 300.00:
            message = f"🚨 <b>ALERTA DE PREÇO BAIXO!</b> 🚨\n\nO Tênis Nike Precision 7 Masculino bateu a sua meta e está por <b>R$ {price:.2f} no Pix!</b>\n\n"
        else:
            message = f"👟 <b>Atualização Diária de Preço</b>\n\nO tênis Nike Precision 7 Masculino está custando:\n<b>R$ {price:.2f} no Pix!</b>\n\n"
            
        if installments_text:
            message += f"💳 Parcelamento: <i>{installments_text}</i>\n\n"
            
        message += f"🛒 Link: {url}"
        
        if bot_token and chat_id:
            send_telegram_message(bot_token, chat_id, message)
        else:
            print("Would have sent message, but no Telegram credentials found.")

    else:
        print("Failed to retrieve the price.")

if __name__ == "__main__":
    main()
