#!/usr/bin/env bash
# Seed the demo household into a storm, then open Harbor signed in as it.
#
# The demo account signs in with demo / 1111. The first run creates it: Maria Lopez in Tampa (two adults, a child,
# a dog, a minivan), her household profile, and Chase and Robinhood connected through Nessie. Later runs reset its
# money and plans. Then it starts the Hurricane Milton scenario, and Harbor, and its AI, plan for the storm.
# Without this script Harbor runs normally, on real time, with no storm.
#
#   ./seed.sh                                   # the server at http://localhost:3000
#   ./seed.sh https://api.example               # another server (it must run with HARBOR_MODE=demo)
#   ./seed.sh https://api.example https://site  # and open the app on a separately hosted site (GitHub Pages)
set -euo pipefail

BASE="${1:-http://localhost:3000}"
SITE="${2:-$BASE}"
API="$BASE/api/v1"
LOGIN='{"email":"demo","password":"1111"}'

post() { curl -fsS -X "$1" "$API$2" -H 'Content-Type: application/json' "${@:3}"; }
token() { sed -n 's/.*"token":"\([^"]*\)".*/\1/p'; }

household() {
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
}

if SIGNED_IN=$(post POST /auth/login -d "$LOGIN" 2>/dev/null); then
  TOKEN=$(printf '%s' "$SIGNED_IN" | token)
  echo "Resetting the demo household's money and plans"
  post POST /demo/reset -o /dev/null
else
  echo "Creating the demo account"
  TOKEN=$(post POST /auth/signup -d '{"name":"Maria Lopez","email":"demo","password":"1111","zip":"33602"}' | token)
  AUTH=(-H "Authorization: Bearer $TOKEN")
  household
fi

echo "Starting the Hurricane Milton scenario"
post POST /demo/start -o /dev/null

URL="$SITE/app#token=$TOKEN"
echo
echo "Signed in as demo (password: 1111)"
echo "$URL"
case "$(uname -s)" in
  Darwin) open "$URL" ;;
  MINGW* | MSYS* | CYGWIN*) start "" "$URL" ;;
  *) xdg-open "$URL" >/dev/null 2>&1 || true ;;
esac
