from datetime import date, timedelta

from vnstock import Vnstock


def main():
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    print("Bat dau ket noi vnstock...")
    print(f"Khoang ngay: {start_date} den {end_date}")

    stock = Vnstock().stock(
        symbol="VNM",
        source="VCI",
    )

    data = stock.quote.history(
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        interval="1D",
    )

    if data is None or data.empty:
        raise RuntimeError("Khong nhan duoc du lieu ma VNM.")

    print("Lay du lieu VNM thanh cong.")
    print(f"So dong du lieu: {len(data)}")
    print(data.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
