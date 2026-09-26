from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from rentals.models import Booking, Equipment


class BookingSerializer(serializers.ModelSerializer):
    """Book equipment of the caller's company. The request in context carries `user` and `company`.

    - `equipment` is given by its code (any case) and must belong to one of the company's branches and not be retired.
    - A booking starts in the future, ends after it starts, and lasts at most 14 days.
    - It cannot overlap another booking of the same equipment; cancelled bookings don't count, and back-to-back
      bookings (one ends exactly when the next starts) are fine.
    - `booked_by` is the user who created the booking; `customer_email` is accepted but never returned.
    - Output: `equipment` is `{"code", "name"}`; `price` is the daily rate times the days booked, where any started day
      counts as a full day, as a string with two decimals; `returned_at` is always present, null until returned.
    """

    equipment = serializers.SlugRelatedField(slug_field="code", queryset=Equipment.objects.all())
    booked_by = serializers.HiddenField(default=serializers.CreateOnlyDefault(serializers.CurrentUserDefault()))
    price = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ["id", "equipment", "booked_by", "customer_email", "start", "end", "cancelled", "returned_at", "price"]
        read_only_fields = ["cancelled", "returned_at"]
        extra_kwargs = {"customer_email": {"write_only": True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and self.instance is None:
            self.fields["equipment"].queryset = Equipment.objects.filter(branch__company=request.company, retired=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and isinstance(data.get("equipment"), str):
            data = {**data, "equipment": data["equipment"].upper()}
        return super().to_internal_value(data)

    def validate_start(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Bookings must start in the future.", code="past_start")
        return value

    def validate(self, attrs):
        start = attrs.get("start", getattr(self.instance, "start", None))
        end = attrs.get("end", getattr(self.instance, "end", None))
        equipment = attrs.get("equipment", getattr(self.instance, "equipment", None))
        if end <= start:
            raise serializers.ValidationError({"end": "The booking must end after it starts."}, code="end_before_start")
        if end - start > timedelta(days=14):
            raise serializers.ValidationError({"end": "Bookings last at most 14 days."}, code="too_long")
        overlapping = Booking.objects.filter(equipment=equipment, cancelled=False, start__lte=end, end__gte=start)
        if self.instance is not None:
            overlapping = overlapping.exclude(pk=self.instance.pk)
        if overlapping.exists():
            raise serializers.ValidationError("The equipment is already booked for that time.", code="overlap")
        return attrs

    def get_price(self, booking):
        days = (booking.end - booking.start).days
        return str((booking.equipment.daily_rate * days).quantize(Decimal("0.01")))

    def to_representation(self, booking):
        data = super().to_representation(booking)
        data["equipment"] = {"code": booking.equipment.code, "name": booking.equipment.name}
        return data
