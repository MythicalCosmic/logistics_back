from django.utils.dateparse import parse_datetime

from base.services.base_service import Validator, ServiceResponse
from base.helpers.auth_helpers import _parse_body
from base.models import Load, LoadLeg, State


def _fail(errors: str) -> tuple:
    return None, ServiceResponse.error(errors)


def _ok(data: dict) -> tuple:
    return data, None


def _parse_dt(value, field_name):
    """Parse a value into a datetime. Returns (datetime, None) or (None, error_str)."""
    if value is None or value == "":
        return None, f"{field_name} is required"
    if not isinstance(value, str):
        return None, f"{field_name} must be a valid ISO datetime string (e.g. 2026-03-05T10:00:00Z)"
    dt = parse_datetime(value)
    if dt is None:
        return None, f"{field_name} must be a valid ISO datetime string (e.g. 2026-03-05T10:00:00Z)"
    return dt, None


VALID_STATUSES = [c[0] for c in Load.Status.choices]
VALID_DRIVER_TYPES = [c[0] for c in Load.DriverType.choices]
VALID_LOAD_TYPES = [c[0] for c in Load.LoadType.choices]
VALID_DIRECTIONS = [c[0] for c in Load.Direction.choices]
VALID_LEG_STATUSES = [c[0] for c in LoadLeg.Status.choices]

def _get_valid_states():
    return set(State.objects.values_list("abbreviation", flat=True))


def create_load_request(request) -> tuple:
    body = _parse_body(request)

    v = Validator()
    v.required(body.get("origin_facility", ""), "Origin facility")
    v.required(body.get("destination_facility", ""), "Destination facility")
    v.required(body.get("origin_state", ""), "Origin state")
    v.required(body.get("destination_state", ""), "Destination state")
    v.required(body.get("origin_datetime", ""), "Origin datetime")
    v.required(body.get("destination_datetime", ""), "Destination datetime")
    v.required(body.get("total_miles"), "Total miles")
    v.required(body.get("payout"), "Payout")

    if not v.is_valid:
        return _fail(v.errors)

    # validate states are real US states
    origin_state = str(body["origin_state"]).strip().upper()
    dest_state = str(body["destination_state"]).strip().upper()
    valid_states = _get_valid_states()

    if origin_state not in valid_states:
        return _fail(f"Invalid origin_state '{origin_state}'. Must be a valid US state abbreviation")
    if dest_state not in valid_states:
        return _fail(f"Invalid destination_state '{dest_state}'. Must be a valid US state abbreviation")

    origin_dt, err = _parse_dt(body.get("origin_datetime"), "Origin datetime")
    if err:
        return _fail(err)

    destination_dt, err = _parse_dt(body.get("destination_datetime"), "Destination datetime")
    if err:
        return _fail(err)

    try:
        total_miles = float(body["total_miles"])
        payout = float(body["payout"])
    except (ValueError, TypeError):
        return _fail("Total miles and payout must be numbers")

    # load_id is NEVER accepted from user — always auto-generated from route
    data = {
        "tour_id": str(body.get("tour_id", "")).strip(),
        "origin_facility": str(body["origin_facility"]).strip(),
        "origin_address": str(body.get("origin_address", "")).strip(),
        "origin_city": str(body.get("origin_city", "")).strip(),
        "origin_state": origin_state,
        "origin_zip": str(body.get("origin_zip", "")).strip(),
        "origin_datetime": origin_dt,
        "origin_timezone": str(body.get("origin_timezone", "")).strip(),
        "destination_facility": str(body["destination_facility"]).strip(),
        "destination_address": str(body.get("destination_address", "")).strip(),
        "destination_city": str(body.get("destination_city", "")).strip(),
        "destination_state": dest_state,
        "destination_zip": str(body.get("destination_zip", "")).strip(),
        "destination_datetime": destination_dt,
        "destination_timezone": str(body.get("destination_timezone", "")).strip(),
        "total_stops": int(body.get("total_stops", 2)),
        "total_miles": total_miles,
        "deadhead_miles": float(body.get("deadhead_miles", 0)),
        "payout": payout,
        "toll": float(body.get("toll", 0)),
        "equipment_type": str(body.get("equipment_type", "53' Trailer")).strip(),
        "equipment_provided": bool(body.get("equipment_provided", True)),
        "duration": str(body.get("duration", "")).strip(),
        "special_services": str(body.get("special_services", "")).strip(),
    }

    if body.get("rate_per_mile") is not None:
        try:
            data["rate_per_mile"] = float(body["rate_per_mile"])
        except (ValueError, TypeError):
            return _fail("Invalid rate_per_mile")

    if body.get("base_rate_per_mile") is not None:
        try:
            data["base_rate_per_mile"] = float(body["base_rate_per_mile"])
        except (ValueError, TypeError):
            return _fail("Invalid base_rate_per_mile")

    driver_type = str(body.get("driver_type", "solo")).strip()
    if driver_type not in VALID_DRIVER_TYPES:
        return _fail(f"Invalid driver_type. Must be one of: {', '.join(VALID_DRIVER_TYPES)}")
    data["driver_type"] = driver_type

    load_type = str(body.get("load_type", "drop")).strip()
    if load_type not in VALID_LOAD_TYPES:
        return _fail(f"Invalid load_type. Must be one of: {', '.join(VALID_LOAD_TYPES)}")
    data["load_type"] = load_type

    direction = str(body.get("direction", "one_way")).strip()
    if direction not in VALID_DIRECTIONS:
        return _fail(f"Invalid direction. Must be one of: {', '.join(VALID_DIRECTIONS)}")
    data["direction"] = direction

    # nested legs
    legs = body.get("legs", [])
    if isinstance(legs, list) and legs:
        validated_legs = []
        for i, leg in enumerate(legs):
            if not isinstance(leg, dict):
                return _fail(f"Leg {i + 1} must be an object")
            lv = Validator()
            lv.required(leg.get("origin_facility", ""), f"Leg {i + 1} origin_facility")
            lv.required(leg.get("destination_facility", ""), f"Leg {i + 1} destination_facility")
            lv.required(leg.get("miles"), f"Leg {i + 1} miles")
            if not lv.is_valid:
                return _fail(lv.errors)
            try:
                leg_miles = float(leg["miles"])
            except (ValueError, TypeError):
                return _fail(f"Leg {i + 1} miles must be a number")

            leg_data = {
                "leg_number": int(leg.get("leg_number", i + 1)),
                "leg_code": str(leg.get("leg_code", "")).strip(),
                "origin_facility": str(leg["origin_facility"]).strip(),
                "destination_facility": str(leg["destination_facility"]).strip(),
                "miles": leg_miles,
                "duration": str(leg.get("duration", "")).strip(),
                "load_type": str(leg.get("load_type", "drop")).strip(),
                "status": str(leg.get("status", "loaded")).strip(),
            }
            if leg.get("payout") is not None:
                try:
                    leg_data["payout"] = float(leg["payout"])
                except (ValueError, TypeError):
                    return _fail(f"Leg {i + 1} payout must be a number")
            validated_legs.append(leg_data)
        data["legs"] = validated_legs

    # nested stops
    stops = body.get("stops", [])
    if isinstance(stops, list) and stops:
        validated_stops = []
        for i, stop in enumerate(stops):
            if not isinstance(stop, dict):
                return _fail(f"Stop {i + 1} must be an object")
            sv = Validator()
            sv.required(stop.get("facility_code", ""), f"Stop {i + 1} facility_code")
            if not sv.is_valid:
                return _fail(sv.errors)
            stop_data = {
                "stop_number": int(stop.get("stop_number", i + 1)),
                "facility_code": str(stop["facility_code"]).strip(),
                "address": str(stop.get("address", "")).strip(),
                "city": str(stop.get("city", "")).strip(),
                "state": str(stop.get("state", "")).strip(),
                "zip_code": str(stop.get("zip_code", "")).strip(),
                "equipment": str(stop.get("equipment", "")).strip(),
                "miles_to_next": None,
            }
            if stop.get("arrival_at"):
                arr_dt, err = _parse_dt(stop["arrival_at"], f"Stop {i + 1} arrival_at")
                if err:
                    return _fail(err)
                stop_data["arrival_at"] = arr_dt
                stop_data["arrival_timezone"] = str(stop.get("arrival_timezone", "")).strip()
            if stop.get("departure_at"):
                dep_dt, err = _parse_dt(stop["departure_at"], f"Stop {i + 1} departure_at")
                if err:
                    return _fail(err)
                stop_data["departure_at"] = dep_dt
                stop_data["departure_timezone"] = str(stop.get("departure_timezone", "")).strip()
            if stop.get("miles_to_next") is not None:
                try:
                    stop_data["miles_to_next"] = float(stop["miles_to_next"])
                except (ValueError, TypeError):
                    return _fail(f"Stop {i + 1} miles_to_next must be a number")
            validated_stops.append(stop_data)
        data["stops"] = validated_stops

    return _ok(data)


def update_load_request(request) -> tuple:
    body = _parse_body(request)

    # load_id is NOT allowed — auto-generated from route
    allowed_fields = {
        "tour_id", "origin_facility", "origin_address", "origin_city",
        "origin_state", "origin_zip", "origin_datetime", "origin_timezone",
        "destination_facility", "destination_address", "destination_city",
        "destination_state", "destination_zip", "destination_datetime",
        "destination_timezone", "total_stops", "total_miles", "deadhead_miles",
        "payout", "toll", "rate_per_mile", "base_rate_per_mile", "driver_type",
        "load_type", "equipment_type", "equipment_provided", "direction",
        "duration", "special_services",
    }

    data = {}
    for field in allowed_fields:
        if field in body:
            data[field] = body[field]

    if not data:
        return _fail("No fields to update")

    # validate states if provided
    valid_states = _get_valid_states()
    if "origin_state" in data:
        origin = str(data["origin_state"]).strip().upper()
        if origin not in valid_states:
            return _fail(f"Invalid origin_state '{origin}'. Must be a valid US state abbreviation")
        data["origin_state"] = origin
    if "destination_state" in data:
        dest = str(data["destination_state"]).strip().upper()
        if dest not in valid_states:
            return _fail(f"Invalid destination_state '{dest}'. Must be a valid US state abbreviation")
        data["destination_state"] = dest

    # validate numeric fields
    numeric_fields = [
        "total_miles", "deadhead_miles", "payout", "toll",
        "rate_per_mile", "base_rate_per_mile",
    ]
    for nf in numeric_fields:
        if nf in data and data[nf] is not None:
            try:
                data[nf] = float(data[nf])
            except (ValueError, TypeError):
                return _fail(f"Invalid {nf}")

    if "total_stops" in data:
        try:
            data["total_stops"] = int(data["total_stops"])
        except (ValueError, TypeError):
            return _fail("Invalid total_stops")

    # validate datetime fields
    for dt_field in ("origin_datetime", "destination_datetime"):
        if dt_field in data:
            dt_val, err = _parse_dt(data[dt_field], dt_field)
            if err:
                return _fail(err)
            data[dt_field] = dt_val

    if "driver_type" in data and data["driver_type"] not in VALID_DRIVER_TYPES:
        return _fail(f"Invalid driver_type. Must be one of: {', '.join(VALID_DRIVER_TYPES)}")
    if "load_type" in data and data["load_type"] not in VALID_LOAD_TYPES:
        return _fail(f"Invalid load_type. Must be one of: {', '.join(VALID_LOAD_TYPES)}")
    if "direction" in data and data["direction"] not in VALID_DIRECTIONS:
        return _fail(f"Invalid direction. Must be one of: {', '.join(VALID_DIRECTIONS)}")

    # strip strings
    for key, val in data.items():
        if isinstance(val, str):
            data[key] = val.strip()

    return _ok(data)


def list_loads_request(request) -> tuple:
    page = request.GET.get("page", "1")
    per_page = request.GET.get("per_page", "20")

    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = min(100, max(1, int(per_page)))
    except (ValueError, TypeError):
        per_page = 20

    data = {
        "page": page,
        "per_page": per_page,
        "status": request.GET.get("status", "").strip(),
        "origin": request.GET.get("origin", "").strip(),
        "destination": request.GET.get("destination", "").strip(),
        "search": request.GET.get("search", "").strip(),
        "sort_by": request.GET.get("sort_by", "-created_at").strip(),
        "route_id": request.GET.get("route_id", "").strip(),
        "group": request.GET.get("group", "").strip().lower() in ("true", "1", "yes"),
    }

    # payout range filters
    min_payout = request.GET.get("min_payout")
    if min_payout:
        try:
            data["min_payout"] = float(min_payout)
        except (ValueError, TypeError):
            return _fail("Invalid min_payout")

    max_payout = request.GET.get("max_payout")
    if max_payout:
        try:
            data["max_payout"] = float(max_payout)
        except (ValueError, TypeError):
            return _fail("Invalid max_payout")

    # date filters
    data["date_from"] = request.GET.get("date_from", "").strip()
    data["date_to"] = request.GET.get("date_to", "").strip()
    data["week"] = request.GET.get("week", "").strip()

    driver_id = request.GET.get("driver_id")
    if driver_id:
        try:
            data["driver_id"] = int(driver_id)
        except (ValueError, TypeError):
            return _fail("Invalid driver_id")

    return _ok(data)


def assign_driver_request(request) -> tuple:
    body = _parse_body(request)
    driver_id = body.get("driver_id")

    v = Validator()
    v.required(driver_id, "driver_id")
    if not v.is_valid:
        return _fail(v.errors)

    try:
        return _ok({"driver_id": int(driver_id)})
    except (ValueError, TypeError):
        return _fail("Invalid driver_id")


def update_status_request(request) -> tuple:
    body = _parse_body(request)
    status = str(body.get("status", "")).strip()

    v = Validator()
    v.required(status, "Status")
    if not v.is_valid:
        return _fail(v.errors)

    if status not in VALID_STATUSES:
        return _fail(f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")

    return _ok({"status": status})
