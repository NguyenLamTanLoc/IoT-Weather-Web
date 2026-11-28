# IoT-Weather-Web
Đồ án dùng mô hình Ensemble kết hợp ARIMA + LSTM + RF để dự đoán nhiệt độ và độ ẩm giúp người dùng đảm bảo sức khoẻ / sản phẩm
- How to install:
  1. Vào folder chính của project chạy docker compose up --build
  2. Khi hoàn thành vào localhost 8000 cho Web và 8001 cho FastAPI
  3. Hệ thống sẽ không thể vẽ biểu đồ do không có dữ liệu của ESP32 DevKit
  4. Run python manage.py seed --live cho dữ liệu mẫu
