import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from base.models import Load, LoadLeg, Stop, Route, State, User


# realistic city/facility data per state
STATE_DATA = {
    "AL": [("Birmingham", "35203"), ("Montgomery", "36104"), ("Huntsville", "35801")],
    "AK": [("Anchorage", "99501"), ("Fairbanks", "99701")],
    "AZ": [("Phoenix", "85001"), ("Tucson", "85701"), ("Mesa", "85201")],
    "AR": [("Little Rock", "72201"), ("Fayetteville", "72701")],
    "CA": [("Los Angeles", "90001"), ("San Francisco", "94102"), ("San Diego", "92101"), ("Sacramento", "95814")],
    "CO": [("Denver", "80201"), ("Colorado Springs", "80901"), ("Aurora", "80010")],
    "CT": [("Hartford", "06101"), ("New Haven", "06510")],
    "DE": [("Wilmington", "19801"), ("Dover", "19901")],
    "FL": [("Miami", "33101"), ("Orlando", "32801"), ("Tampa", "33601"), ("Jacksonville", "32099")],
    "GA": [("Atlanta", "30301"), ("Savannah", "31401"), ("Augusta", "30901")],
    "HI": [("Honolulu", "96801")],
    "ID": [("Boise", "83701"), ("Nampa", "83651")],
    "IL": [("Chicago", "60601"), ("Springfield", "62701"), ("Rockford", "61101")],
    "IN": [("Indianapolis", "46201"), ("Fort Wayne", "46801")],
    "IA": [("Des Moines", "50301"), ("Cedar Rapids", "52401")],
    "KS": [("Wichita", "67201"), ("Kansas City", "66101")],
    "KY": [("Louisville", "40201"), ("Lexington", "40502")],
    "LA": [("New Orleans", "70112"), ("Baton Rouge", "70801")],
    "ME": [("Portland", "04101"), ("Bangor", "04401")],
    "MD": [("Baltimore", "21201"), ("Annapolis", "21401")],
    "MA": [("Boston", "02101"), ("Worcester", "01601")],
    "MI": [("Detroit", "48201"), ("Grand Rapids", "49501")],
    "MN": [("Minneapolis", "55401"), ("Saint Paul", "55101")],
    "MS": [("Jackson", "39201"), ("Gulfport", "39501")],
    "MO": [("Kansas City", "64101"), ("St. Louis", "63101")],
    "MT": [("Billings", "59101"), ("Missoula", "59801")],
    "NE": [("Omaha", "68101"), ("Lincoln", "68501")],
    "NV": [("Las Vegas", "89101"), ("Reno", "89501")],
    "NH": [("Manchester", "03101"), ("Concord", "03301")],
    "NJ": [("Newark", "07101"), ("Jersey City", "07302"), ("Trenton", "08601")],
    "NM": [("Albuquerque", "87101"), ("Santa Fe", "87501")],
    "NY": [("New York", "10001"), ("Buffalo", "14201"), ("Albany", "12201")],
    "NC": [("Charlotte", "28201"), ("Raleigh", "27601"), ("Greensboro", "27401")],
    "ND": [("Fargo", "58102"), ("Bismarck", "58501")],
    "OH": [("Columbus", "43201"), ("Cleveland", "44101"), ("Cincinnati", "45201")],
    "OK": [("Oklahoma City", "73101"), ("Tulsa", "74101")],
    "OR": [("Portland", "97201"), ("Eugene", "97401")],
    "PA": [("Philadelphia", "19101"), ("Pittsburgh", "15201"), ("Harrisburg", "17101")],
    "RI": [("Providence", "02901")],
    "SC": [("Charleston", "29401"), ("Columbia", "29201")],
    "SD": [("Sioux Falls", "57101"), ("Rapid City", "57701")],
    "TN": [("Nashville", "37201"), ("Memphis", "38101"), ("Knoxville", "37901")],
    "TX": [("Dallas", "75201"), ("Houston", "77001"), ("San Antonio", "78201"), ("Austin", "73301")],
    "UT": [("Salt Lake City", "84101"), ("Provo", "84601")],
    "VT": [("Burlington", "05401"), ("Montpelier", "05601")],
    "VA": [("Richmond", "23218"), ("Virginia Beach", "23450"), ("Norfolk", "23501")],
    "WA": [("Seattle", "98101"), ("Tacoma", "98401"), ("Spokane", "99201")],
    "WV": [("Charleston", "25301"), ("Huntington", "25701")],
    "WI": [("Milwaukee", "53201"), ("Madison", "53701")],
    "WY": [("Cheyenne", "82001"), ("Casper", "82601")],
}

FACILITY_TYPES = ["WH", "DC", "FC", "SC", "XD"]
EQUIPMENT_TYPES = ["53' Trailer", "48' Trailer", "Flatbed", "Reefer", "Box Truck"]
SPECIAL_SERVICES_OPTIONS = [
    "", "", "",  # most loads have none
    "Hazmat", "Team Required", "Liftgate", "Appointment Required",
    "Inside Delivery", "White Glove",
]

# popular lanes (weighted more heavily)
POPULAR_LANES = [
    ("TX", "CA"), ("CA", "TX"), ("TX", "FL"), ("FL", "TX"),
    ("IL", "TX"), ("TX", "IL"), ("CA", "WA"), ("WA", "CA"),
    ("GA", "FL"), ("FL", "GA"), ("NY", "PA"), ("PA", "NY"),
    ("OH", "IL"), ("IL", "OH"), ("TX", "GA"), ("GA", "TX"),
    ("CA", "AZ"), ("AZ", "CA"), ("NC", "GA"), ("GA", "NC"),
    ("TX", "NY"), ("NY", "TX"), ("CA", "NV"), ("NV", "CA"),
    ("FL", "NC"), ("NC", "FL"), ("PA", "NJ"), ("NJ", "PA"),
    ("IL", "IN"), ("IN", "IL"), ("CO", "TX"), ("TX", "CO"),
    ("WA", "OR"), ("OR", "WA"), ("TN", "GA"), ("GA", "TN"),
    ("MO", "IL"), ("IL", "MO"), ("VA", "NC"), ("NC", "VA"),
]


class Command(BaseCommand):
    help = "Seed ~500 realistic fake loads across US routes"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=500, help="Number of loads")
        parser.add_argument("--clear", action="store_true", help="Clear existing loads first")

    def handle(self, *args, **options):
        count = options["count"]

        if options["clear"]:
            Stop.objects.all().delete()
            LoadLeg.objects.all().delete()
            Load.objects.all().delete()
            Route.objects.all().delete()
            self.stdout.write("Cleared existing loads and routes")

        # ensure states exist
        if State.objects.count() == 0:
            self.stderr.write(self.style.ERROR("No states found. Run seed_states first."))
            return

        # get or create a user to register loads
        user, _ = User.objects.get_or_create(
            email="system@logistics.com",
            defaults={
                "first_name": "System",
                "last_name": "Seeder",
                "password": "not-a-real-password",
            },
        )

        all_states = list(STATE_DATA.keys())
        now = timezone.now()

        loads_to_create = []
        route_cache = {}

        for i in range(count):
            # 60% popular lanes, 40% random
            if random.random() < 0.6 and POPULAR_LANES:
                origin_abbr, dest_abbr = random.choice(POPULAR_LANES)
            else:
                origin_abbr = random.choice(all_states)
                dest_abbr = random.choice([s for s in all_states if s != origin_abbr])

            # get or create route
            route_key = f"{origin_abbr}-{dest_abbr}"
            if route_key not in route_cache:
                route_cache[route_key] = Route.get_or_create_route(origin_abbr, dest_abbr)
            route = route_cache[route_key]

            # pick cities
            origin_city, origin_zip = random.choice(STATE_DATA[origin_abbr])
            dest_city, dest_zip = random.choice(STATE_DATA[dest_abbr])

            # facility codes
            fac_type_o = random.choice(FACILITY_TYPES)
            fac_type_d = random.choice(FACILITY_TYPES)
            origin_fac = f"{fac_type_o}-{origin_abbr}-{random.randint(100, 999)}"
            dest_fac = f"{fac_type_d}-{dest_abbr}-{random.randint(100, 999)}"

            # realistic miles based on distance (rough)
            base_miles = random.randint(150, 2800)
            total_miles = Decimal(str(base_miles + random.randint(0, 50)))

            # payout scales with miles: $1.50-$4.00 per mile
            rate = Decimal(str(round(random.uniform(1.50, 4.00), 2)))
            payout = round(total_miles * rate, 2)
            toll = Decimal(str(round(random.uniform(0, 85), 2)))

            # time spread: loads created over the past 90 days
            days_ago = random.randint(0, 90)
            hours_offset = random.randint(0, 23)
            created_offset = timedelta(days=days_ago, hours=hours_offset)
            origin_dt = now - created_offset
            # transit time: rough 1 hour per 55 miles
            transit_hours = max(3, int(float(total_miles) / 55))
            dest_dt = origin_dt + timedelta(hours=transit_hours)
            duration = f"{transit_hours}h {random.randint(0, 59)}m"

            # status distribution: 40% available, 20% booked, 15% in_transit, 20% delivered, 5% cancelled
            status_roll = random.random()
            if status_roll < 0.40:
                status = "available"
            elif status_roll < 0.60:
                status = "booked"
            elif status_roll < 0.75:
                status = "in_transit"
            elif status_roll < 0.95:
                status = "delivered"
            else:
                status = "cancelled"

            equipment = random.choice(EQUIPMENT_TYPES)
            driver_type = random.choice(["solo", "solo", "solo", "team"])  # 75% solo
            load_type = random.choice(["drop", "drop", "live", "hook"])
            direction = random.choice(["one_way", "one_way", "one_way", "round_trip"])
            special = random.choice(SPECIAL_SERVICES_OPTIONS)

            deadhead = Decimal(str(round(random.uniform(0, 80), 2)))

            loads_to_create.append(Load(
                load_id=route.route_id,
                tour_id=f"TR-{random.randint(10000, 99999)}",
                route=route,
                origin_facility=origin_fac,
                origin_address=f"{random.randint(100, 9999)} {random.choice(['Main', 'Industrial', 'Commerce', 'Logistics', 'Freight', 'Distribution'])} {random.choice(['St', 'Blvd', 'Dr', 'Ave', 'Pkwy'])}",
                origin_city=origin_city,
                origin_state=origin_abbr,
                origin_zip=origin_zip,
                origin_datetime=origin_dt,
                origin_timezone="UTC",
                destination_facility=dest_fac,
                destination_address=f"{random.randint(100, 9999)} {random.choice(['Warehouse', 'Terminal', 'Park', 'Center', 'Hub', 'Gateway'])} {random.choice(['Rd', 'Way', 'Ln', 'Ct', 'Loop'])}",
                destination_city=dest_city,
                destination_state=dest_abbr,
                destination_zip=dest_zip,
                destination_datetime=dest_dt,
                destination_timezone="UTC",
                total_stops=random.choice([2, 2, 2, 3, 3, 4]),
                total_miles=total_miles,
                deadhead_miles=deadhead,
                payout=payout,
                rate_per_mile=rate,
                base_rate_per_mile=rate - Decimal("0.15"),
                toll=toll,
                driver_type=driver_type,
                load_type=load_type,
                equipment_type=equipment,
                equipment_provided=random.choice([True, True, True, False]),
                direction=direction,
                duration=duration,
                status=status,
                special_services=special,
                registered_by=user,
            ))

        Load.objects.bulk_create(loads_to_create)

        # summary
        route_count = Route.objects.count()
        load_count = Load.objects.count()

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {count} loads across {route_count} routes. "
            f"Total loads in DB: {load_count}"
        ))

        # top 5 routes
        top = (
            Route.objects
            .annotate(lc=Count("loads"))
            .order_by("-lc")[:5]
        )
        for r in top:
            self.stdout.write(f"  {r.route_id}: {r.lc} loads")
