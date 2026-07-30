from datetime import date, timedelta

from vnstock.api.quote import Quote


def main() -> None:
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    print("Bat dau ket noi Vnstock API moi...")
    print(f"Khoang ngay: {start_date} den {end_date}")

    quote = Quote(
        symbol="VNM",
        source="VCI",
    )

    data = quote.history(
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        interval="1D",
    )

    if data is None or data.empty:
        raise RuntimeError("Khong nhan duoc du lieu ma VNM.")

    print("Lay du lieu VNM bang API moi thanh cong.")
    print(f"So dong du lieu: {len(data)}")
    print(data.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
