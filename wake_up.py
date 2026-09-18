import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

URL = "https://vista-ai-control-ihf62k8irzuqek2vmfkf66.streamlit.app"

# Configure Headless Chrome for Linux Server
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)

try:
    print(f"Connecting to Streamlit App: {URL}")
    driver.get(URL)
    time.sleep(5)  # Allow page elements to render

    # Locate the wake-up button on Streamlit's hibernation page
    wake_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Yes, get this app back up')]")
    
    if wake_buttons:
        print("Sleeping app detected! Clicking the wake-up button...")
        wake_buttons[0].click()
        time.sleep(10)
        print("Wake-up signal sent successfully.")
    else:
        print("App is already awake and operational!")

except Exception as e:
    print(f"Script encountered an error: {e}")

finally:
    driver.quit()
