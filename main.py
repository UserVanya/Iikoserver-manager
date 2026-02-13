"""Пример использования iikoserver API клиента."""

import asyncio
import logging

from iikoserver import IikoServerApiClientManager, get_iikoserver_config

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def main() -> None:
    """Основная функция."""
    # Загружаем конфигурацию из config.yml
    config = get_iikoserver_config()
    print(f"Подключение к серверу: {config.host}")

    # Создаём менеджер API
    manager = await IikoServerApiClientManager.from_config(config)

    try:
        # Получаем типы скидок
        order_types = await manager.get_order_types_list()
        print(f"\nТипы заказов ({len(order_types)} шт.):")
        for ot in order_types[:5]:  # Показываем первые 5
            print(f"  - {ot.name} (id: {ot.id})")

    finally:
        # Закрываем все соединения
        await IikoServerApiClientManager.close_all()
        print("\nСоединения закрыты.")


if __name__ == "__main__":
    asyncio.run(main())
