#インポート類
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome import service
from selenium.webdriver.common.by import By
from time import sleep

def login_ideascale():


    chrome_options = Options()

    # ブラウザを起動
    
    driver = webdriver.Chrome(options=chrome_options)
    
    #ウインドウを最大化する
    driver.maximize_window()
    url = "https://projectcatalyst.io/"
    # URLを開く
    driver.get(url)
    sleep(2)

    #Cookie承諾
    
    agree_css_selector = '/html/body/div[1]/div[2]/button'
    agree_button_element = driver.find_element(By.XPATH, value=agree_css_selector)

    # ログインボタンをクリック
    agree_button_element.click()

    #ページリロード待ち
    sleep(1)
    
    return driver