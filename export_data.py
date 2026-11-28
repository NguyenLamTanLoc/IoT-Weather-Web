from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from monitor import exports


def parse_local(text):
    try:
        return timezone.make_aware(datetime.strptime(text, "%Y-%m-%d %H:%M"))
    except ValueError:
        raise CommandError('Sai định dạng giờ, cần dạng "2026-11-21 14:00"')


class Command(BaseCommand):
    help = "Xuất số liệu ra file CSV (thống kê) và JSON (cho AI)"

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=60, help="Xuất N phút gần nhất (mặc định 60)")
        parser.add_argument("--start", help='Giờ bắt đầu theo giờ địa phương, vd "2026-11-21 14:00"')
        parser.add_argument("--end", help="Giờ kết thúc (mặc định: bây giờ)")
        parser.add_argument("--out", help="Thư mục lưu (mặc định: exports/)")

    def handle(self, *args, **o):
        end = parse_local(o["end"]) if o["end"] else timezone.now()
        start = parse_local(o["start"]) if o["start"] else end - timedelta(minutes=o["minutes"])
        if start >= end:
            raise CommandError("Giờ bắt đầu phải trước giờ kết thúc")
        result = exports.export_range(start, end, o["out"])
        if result is None:
            self.stdout.write(self.style.WARNING("Không có số liệu nào trong khoảng này."))
            return
        csv_path, json_path, count = result
        self.stdout.write(self.style.SUCCESS(f"Đã xuất {count} lượt đo:"))
        self.stdout.write(f"  CSV : {csv_path}")
        self.stdout.write(f"  JSON: {json_path}")
