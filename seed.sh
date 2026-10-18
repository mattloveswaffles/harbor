#!/usr/bin/env bash
# Seed a household into a storm, then open Harbor signed in as them.
#
# Signs up Maria Lopez (Tampa: two adults, a child, a dog, a minivan), saves her household profile, connects
# Chase and Robinhood through Nessie, and starts the Hurricane Milton scenario. Harbor, and its AI, then plan
# for the storm. Without this script Harbor runs normally, on real time, with no storm.
#
#   ./seed.sh                        # against http://localhost:3000
#   ./seed.sh https://harbor.example # another server (it must run with HARBOR_MODE=demo)
set -euo pipefail

BASE="${1:-http://localhost:3000}"
API="$BASE/api/v1"
STAMP="$(date +%s)"
EMAIL="maria.$STAMP@example.com"
PASSWORD="harbor-$STAMP"

post() { curl -fsS -X "$1" "$API$2" -H 'Content-Type: application/json' "${@:3}"; }

echo "Signing up $EMAIL"
SIGNUP=$(post POST /auth/signup -d "{\"name\":\"Maria Lopez\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"zip\":\"33602\"}")
TOKEN=$(printf '%s' "$SIGNUP" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
AUTH=(-H "Authorization: Bearer $TOKEN")

echo "Saving the household"
post PUT /me/profile "${AUTH[@]}" -o /dev/null -d @- <<'JSON'
{
  "personal": {"name": "Maria Lopez", "dob": "1987-03-14", "phone": "(813) 555-0142"},
  "home": {"address": "412 E Madison St, Tampa, FL 33602", "home_type": "house", "evac_zone": "A"},
  "people": [
    {"name": "Maria Lopez", "age": 37, "relation": "you"},
    {"name": "Daniel Lopez", "age": 40, "relation": "spouse"},
    {"name": "Sofia Lopez", "age": 7, "relation": "child"}
  ],
  "pets": [{"name": "Biscuit", "type": "dog", "weight_lb": 45, "notes": "crate trained"}],
  "medical": {
    "medications": [
      {"name": "Metformin", "dose": "500 mg", "person": "Maria", "schedule": "Twice a day", "days_left": 21},
      {"name": "Lisinopril", "dose": "10 mg", "person": "Daniel", "schedule": "Mornings", "days_left": 4},
      {"name": "Albuterol inhaler", "person": "Sofia", "schedule": "As needed", "days_left": 30}
    ],
    "equipment": ["CPAP (Daniel)"],
    "allergies": "Sofia: penicillin",
    "pharmacy": "CVS, 1101 N Florida Ave, Tampa"
  },
  "vehicle": {"make_model": "2018 Toyota Sienna", "mpg": 21, "tank_gal": 20, "fuel_level": 0.5, "seats": 7},
  "places": [{"label": "Rosa's house", "address": "1840 Vineville Ave, Macon, GA 31201", "kind": "destination"}],
  "contacts": [{"name": "Rosa Lopez", "relation": "sister", "phone": "(478) 555-0199", "gets_plan": true}]
}
JSON

for bank in chase robinhood; do
  echo "Connecting $bank through Nessie"
  post POST "/me/connections/$bank" "${AUTH[@]}" -o /dev/null
done

echo "Starting the Hurricane Milton scenario"
post POST /demo/start -o /dev/null

URL="$BASE/app#token=$TOKEN"
echo
echo "Signed in as $EMAIL (password: $PASSWORD)"
echo "$URL"
case "$(uname -s)" in
  Darwin) open "$URL" ;;
  MINGW* | MSYS* | CYGWIN*) start "" "$URL" ;;
  *) xdg-open "$URL" >/dev/null 2>&1 || true ;;
esac
