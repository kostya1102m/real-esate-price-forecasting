import time
import random
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
)
from loguru import logger

try:
    from selenium_stealth import stealth

    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    logger.warning(
        "selenium-stealth не установлен: "
        "pip install selenium-stealth"
    )


USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
        "Gecko/20100101 Firefox/133.0"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
]


class CaptchaDetectedError(Exception):
    def __init__(self, url: str):
        self.url = url
        super().__init__(f"CAPTCHA detected: {url}")


class BrowserManager:
    def __init__(
        self,
        headless: bool = True,
        window_size: tuple[int, int] = (1920, 1080),
        page_load_timeout: int = 30,
        implicit_wait: int = 10,
        user_data_dir: Optional[str] = None,
        rotate_ua_every: int = 10,
    ):
        """
        Args:
            headless: запускать без GUI
            window_size: размер окна браузера
            page_load_timeout: таймаут загрузки страницы (сек)
            implicit_wait: неявное ожидание элементов (сек)
            user_data_dir: путь к профилю Chrome
            rotate_ua_every: менять User-Agent каждые N страниц
        """
        self.headless = headless
        self.window_size = window_size
        self.page_load_timeout = page_load_timeout
        self.implicit_wait = implicit_wait
        self.user_data_dir = user_data_dir
        self.rotate_ua_every = rotate_ua_every

        self._driver: Optional[webdriver.Chrome] = None
        self._current_ua: str = random.choice(USER_AGENTS)
        self._page_count = 0

    def _build_options(self) -> Options:
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        w, h = self.window_size
        options.add_argument(f"--window-size={w},{h}")

    
        options.add_argument(
            "--disable-blink-features=AutomationControlled"
        )
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")

        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )
        options.add_experimental_option(
            "useAutomationExtension", False
        )

        options.add_argument("--lang=ru-RU")
        options.add_argument(
            "--accept-lang=ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        )

        if self.user_data_dir:
            options.add_argument(
                f"--user-data-dir={self.user_data_dir}"
            )

        options.add_argument(f"user-agent={self._current_ua}")

        return options

    def _apply_stealth(self, driver: webdriver.Chrome) -> None:
        if HAS_STEALTH:
            stealth(
                driver,
                languages=["ru-RU", "ru", "en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
        else:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                        Object.defineProperty(
                            navigator, 'webdriver', {
                                get: () => undefined
                            }
                        );
                        Object.defineProperty(
                            navigator, 'plugins', {
                                get: () => [1, 2, 3, 4, 5]
                            }
                        );
                        Object.defineProperty(
                            navigator, 'languages', {
                                get: () => ['ru-RU', 'ru', 'en-US', 'en']
                            }
                        );
                        window.chrome = { runtime: {} };

                        const originalQuery = 
                            window.navigator.permissions.query;
                        window.navigator.permissions.query = (
                            parameters
                        ) => (
                            parameters.name === 'notifications'
                                ? Promise.resolve({
                                    state: Notification.permission
                                  })
                                : originalQuery(parameters)
                        );
                    """
                },
            )

    def start(self) -> webdriver.Chrome:
        if self._driver:
            logger.debug("Браузер уже запущен")
            return self._driver

        logger.info(
            f"🌐 Запуск Chrome "
            f"(headless={self.headless}, "
            f"UA={self._current_ua[:50]}...)"
        )

        options = self._build_options()

        try:
            self._driver = webdriver.Chrome(options=options)
            self._driver.set_page_load_timeout(
                self.page_load_timeout
            )
            self._driver.implicitly_wait(self.implicit_wait)
            self._apply_stealth(self._driver)

            logger.info("Chrome запущен")
            return self._driver

        except WebDriverException as e:
            logger.error(f"Не удалось запустить Chrome: {e}")
            raise

    def stop(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
                logger.info("Chrome остановлен")
            except Exception as e:
                logger.warning(f"Ошибка при остановке: {e}")
            finally:
                self._driver = None

    def restart_with_new_ua(self) -> None:
        old_ua = self._current_ua
        available = [ua for ua in USER_AGENTS if ua != old_ua]
        self._current_ua = random.choice(available)

        logger.info(
            f" Ротация User-Agent: "
            f"...{self._current_ua[-30:]}"
        )

        self.stop()
        time.sleep(random.uniform(2, 5))
        self.start()

    @property
    def driver(self) -> webdriver.Chrome:
        if not self._driver:
            return self.start()
        return self._driver

    def get_page(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        wait_timeout: int = 15,
        scroll: bool = True,
    ) -> str:
        """
        Загружает страницу, эмулирует поведение пользователя
        и возвращает HTML.

        Args:
            url: URL страницы
            wait_selector: CSS-селектор для Explicit Wait
            wait_timeout: таймаут ожидания элемента (сек)
            scroll: эмулировать скролл страницы

        Returns:
            HTML-код страницы

        Raises:
            CaptchaDetectedError: при обнаружении CAPTCHA
        """
        self._page_count += 1

        if (
            self._page_count > 1
            and self._page_count % self.rotate_ua_every == 0
        ):
            self.restart_with_new_ua()

        driver = self.driver
        logger.debug(f"📄 Загрузка: {url[:80]}...")

        driver.get(url)

        if wait_selector:
            try:
                WebDriverWait(driver, wait_timeout).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, wait_selector)
                    )
                )
                logger.debug(
                    f"✓ Элемент '{wait_selector}' найден"
                )
            except TimeoutException:
                logger.warning(
                    f"⚠️ Элемент '{wait_selector}' "
                    f"не найден за {wait_timeout} сек"
                )

        if scroll:
            self._simulate_reading(driver)

        html = driver.page_source

        if self._is_captcha(html):
            logger.warning(f"🔒 CAPTCHA на {url[:60]}...")
            raise CaptchaDetectedError(url)

        return html

    def _simulate_reading(self, driver: webdriver.Chrome) -> None:
        """
        Эмуляция чтения: скролл вниз с паузами.
        Имитирует пользователя, просматривающего объявления.
        """
        try:
            viewport_height = driver.execute_script(
                "return window.innerHeight"
            )
            page_height = driver.execute_script(
                "return document.body.scrollHeight"
            )

            if page_height <= viewport_height:
                time.sleep(random.uniform(1.0, 2.0))
                return

            num_scrolls = random.randint(2, 4)
            scroll_step = page_height / (num_scrolls + 1)

            current_pos = 0
            for i in range(num_scrolls):
                # cкроллим на случайное расстояние
                scroll_amount = scroll_step * random.uniform(0.7, 1.3)
                current_pos += scroll_amount
                current_pos = min(current_pos, page_height)

                driver.execute_script(
                    f"window.scrollTo({{top: {int(current_pos)}, "
                    f"behavior: 'smooth'}});"
                )

                time.sleep(random.uniform(1.0, 3.0))

            if random.random() < 0.3:
                scroll_back = current_pos * random.uniform(0.2, 0.5)
                driver.execute_script(
                    f"window.scrollTo({{top: {int(scroll_back)}, "
                    f"behavior: 'smooth'}});"
                )
                time.sleep(random.uniform(0.5, 1.5))

            driver.execute_script(
                "window.scrollTo({top: 0, behavior: 'smooth'});"
            )
            time.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            logger.debug(f"Ошибка эмуляции скролла: {e}")

    def simulate_mouse_movement(
        self, driver: webdriver.Chrome
    ) -> None:
        try:
            actions = ActionChains(driver)
            body = driver.find_element(By.TAG_NAME, "body")

            for _ in range(random.randint(2, 3)):
                x_offset = random.randint(-200, 200)
                y_offset = random.randint(-100, 100)

                try:
                    actions.move_to_element_with_offset(
                        body, x_offset, y_offset
                    ).perform()
                except Exception:
                    pass

                time.sleep(random.uniform(0.3, 0.8))

        except Exception as e:
            logger.debug(f"Ошибка движения мыши: {e}")

    def _is_captcha(self, html: str) -> bool:
        html_lower = html[:5000].lower()
        indicators = [
            "captcha",
            "я не робот",
            "i'm not a robot",
            "проверка безопасности",
            "access denied",
            "заблокирован",
            "подозрительная активность",
            "security check",
        ]
        return any(ind in html_lower for ind in indicators)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

    def __del__(self):
        self.stop()