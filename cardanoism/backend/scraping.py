#インポート類
from selenium import webdriver
from selenium.webdriver.chrome import service
from selenium.webdriver.common.by import By
from time import sleep

def login_ideascale():

    #driver設定および起動設定
    chromedriver = "C:\chromedriver\chromedriver.exe"
    chrome_service = service.Service(executable_path=chromedriver)
    driver = webdriver.Chrome(service=chrome_service)
    driver.get('https://cardano.ideascale.com/')
    sleep(5)

    #Cookie承諾
    agree_css_selector = "body > div:nth-child(8) > div > div.modal.fade.show > div > div > div.modal-body > div > div.col-md-auto.py-2.d-flex.align-items-center > button.btn.btn-primary.flex-fill"
    agree_button_element = driver.find_element(By.CSS_SELECTOR, value=agree_css_selector)

    # ログインボタンをクリック
    agree_button_element.click()

    #ページリロード待ち
    sleep(5)

    #ログインボタンクリック

    login_css_selector = "#root > div.fixed-top > nav > div > ul > li:nth-child(3) > button"
    login_button_element = driver.find_element(By.CSS_SELECTOR, value=login_css_selector)

    login_button_element.click()
    sleep(5)


    #ideascaleログイン

    # コピーした「ユーザー名 または メールアドレス」入力欄のCSSセレクタを文字列に格納
    input_user_selector = "#login-email"
    # コピーした「パスワード」入力欄のCSSセレクタを文字列に格納
    input_password_selector = "#login-password"

    input_user_element = driver.find_element(By.CSS_SELECTOR, value=input_user_selector)
    # 「ユーザー名 または メールアドレス」を入力
    input_user_element.send_keys("contact@cardanoism.com")

    input_password_element = driver.find_element(By.CSS_SELECTOR, value=input_password_selector)
    # 「パスワード」を入力
    input_password_element.send_keys("*hRhy3DPX99LX")

    input_password_element.submit()
    
    sleep(5)
    
    return driver

