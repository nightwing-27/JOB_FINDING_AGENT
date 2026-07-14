import streamlit as st
import urllib.parse
import urllib.request
import urllib.error
import json
import re
import html 
import time 
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="Career Agent", page_icon="🤖")

st.markdown("""
    <style>
    .agent-box { background-color: #f0f7ff; border-left: 4px solid #007bff; padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; }
    .job-card { padding: 10px 0px; }
    .company-logo { width: 45px; border-radius: 50%; float: left; margin-right: 15px; border: 1px solid #e9ecef; }
    .job-title { margin: 0; padding-top: 5px; font-size: 18px; font-weight: 600; }
    .job-subtitle { color: #555; font-size: 14px; margin-bottom: 10px; }
    .privacy-badge { text-align: center; font-size: 12px; color: #6c757d; margin-top: 20px; }
    </style>
    """, unsafe_allow_html=True)

# ⚡ SECURE DUAL-KEY VAULT 
try:
    SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
except KeyError:
    st.error("🚨 Security Alert: SERPAPI_KEY is missing! Please check your Streamlit Secrets.")
    st.stop()

# 🔄 Load Balancing: Grab all available Gemini Keys
GEMINI_KEYS = []
if "GEMINI_API_KEY_1" in st.secrets: GEMINI_KEYS.append(st.secrets["GEMINI_API_KEY_1"])
if "GEMINI_API_KEY_2" in st.secrets: GEMINI_KEYS.append(st.secrets["GEMINI_API_KEY_2"])
if "GEMINI_API_KEY" in st.secrets: GEMINI_KEYS.append(st.secrets["GEMINI_API_KEY"]) # Fallback for old name

if not GEMINI_KEYS:
    st.error("🚨 Security Alert: No Gemini API Keys found in vault!")
    st.stop()

BANNED_BOARDS = ["jooble", "talent.com", "foundit", "jobrapido", "bebee", "adzuna", "getmereferred", "kit job", "trabajo", "jobaaj", "simplyhired", "apna", "cutshort", "lensa", "ziprecruiter"]
BANNED_TITLE_WORDS = ["salary up to", "lpa", "freshers jobs", "fresher jobs", "hiring freshers", "100%", "guaranteed", "walk-in", "walk in", "course bhai", "urgent hiring"]

if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = 0

# 🧠 THE DUAL-KEY "WATERFALL" ROUTER
def call_ai_fallback(prompt, system_instruction):
    gemini_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    
    # Iterate through all available API keys
    for i, key in enumerate(GEMINI_KEYS):
        # Iterate through models (Newest to Oldest)
        for model in gemini_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                payload = json.dumps({"contents": [{"parts": [{"text": f"{system_instruction}\n\nUser: {prompt}"}]}]}).encode('utf-8')
                req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    res = json.loads(response.read().decode())
                    txt = res['candidates'][0]['content']['parts'][0]['text']
                    return json.loads(re.sub(r"```json|```", "", txt).strip())
            except urllib.error.HTTPError as e:
                # If rate-limited (429) or quota exceeded/bad request (400, 403), jump to the NEXT API KEY immediately
                if e.code in [429, 403, 400]:
                    if len(GEMINI_KEYS) > 1 and i < len(GEMINI_KEYS) - 1:
                        st.toast(f"Key {i+1} Limit Reached! Hot-swapping to Backup Key...", icon="🔄")
                    break 
                continue # For other errors, just try the older model
            except Exception:
                continue 

    # If ALL keys and ALL models fail:
    st.error("🚨 CRITICAL: All API keys and Gemini models rejected the request. Limits exceeded.")
    return None

def find_corporate_url(company, role):
    search_term = f"{company} careers {role}".replace("Any Role", "").strip()
    query = urllib.parse.quote(search_term)
    url = f"https://serpapi.com/search.json?engine=google&q={query}&hl=en&api_key={SERPAPI_KEY}&num=3"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            for result in data.get("organic_results", []):
                link = result.get("link", "")
                if "linkedin.com" not in link and "indeed.com" not in link and "naukri.com" not in link:
                    return link
    except: pass
    return None

def playwright_scrape_and_parse(url, company):
    st.toast(f"Deploying invisible browser to {url}...", icon="🌐")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=20000)
            page.wait_for_timeout(3000)
            raw_text = page.inner_text("body")
        except:
            raw_text = ""
        finally:
            browser.close()
            
    if not raw_text: return []
    st.toast(f"Ripped {len(raw_text)} characters. Handing to AI...", icon="🧠")
    
    system_instruction = "Extract all job listings from this messy text. Return ONLY a raw JSON list of objects with keys: 'title', 'location' (explicitly write Remote, Hybrid, or Offline if mentioned), 'type'. If none, return []."
    prompt = f"Text to parse: {raw_text[:15000]}"
    
    result = call_ai_fallback(prompt, system_instruction)
    return result if result else []

with st.sidebar:
    st.title("⚙️ Search Filters")
    st.caption("Refine your agent's parameters.")
    
    st.markdown("**Role Details**")
    filter_type = st.selectbox("Job Type", ["Any / Optional", "Full Time", "Part Time", "Contract", "Internship", "Freelance"])
    filter_setup = st.selectbox("Work Setup", ["Any / Optional", "Remote / WFH", "Hybrid", "Offline / On-site"])
    
    st.markdown("**Platform Rules**")
    filter_platform = st.selectbox("Target Platform", ["Auto-Detect (Best)", "Corporate Site Only", "Open Job Boards Only"])
        
    st.markdown("**Geographic Targeting**")
    filter_loc = st.selectbox("Region / Country", ["Any Region / Optional", "Work from Anywhere (Global)", "India", "USA", "UK", "Europe", "APAC"])
    
    lock_inputs = filter_loc == "Work from Anywhere (Global)"
    filter_state = st.text_input("State / Province", value="" if not lock_inputs else "N/A", placeholder="Optional" if not lock_inputs else "", disabled=lock_inputs)
    filter_city = st.text_input("City", value="" if not lock_inputs else "N/A", placeholder="Optional" if not lock_inputs else "", disabled=lock_inputs)
    
    st.markdown("<div class='privacy-badge'>🔒 Zero-Log Policy Active.<br>Your searches are not tracked or stored.</div>", unsafe_allow_html=True)

st.title("🤖 Career Agent")
st.caption("AI-Powered Job Hunting")

raw_user_prompt = st.chat_input("e.g., paid non tech internships in mumbai...")

if raw_user_prompt:
    
    current_time = time.time()
    time_since_last = current_time - st.session_state.last_request_time
    if time_since_last < 5.0:
        st.error(f"🛑 Security Alert: Please wait {int(5 - time_since_last)} seconds before sending another request to prevent API spam.")
        st.stop()
    st.session_state.last_request_time = current_time

    safe_prompt = html.escape(raw_user_prompt).strip()
    if len(safe_prompt) > 300:
        safe_prompt = safe_prompt[:300]

    with st.chat_message("user"):
        st.write(safe_prompt)
        
    with st.chat_message("assistant"):
        with st.spinner("🧠 Analyzing intent securely..."):
            system_instruction = """
            Extract search parameters. Return ONLY raw JSON (no backticks):
            "company" (string, specific company mentioned, or empty if none),
            "role" (string, the job title),
            "geography" (string, ONLY geographical places like city, state, or country. e.g., 'Mumbai', 'India'. Empty if none),
            "work_setup" (string, ONLY 'Remote', 'Hybrid', 'Offline', or empty),
            "experience" (string, e.g., 'Fresher', 'Internship', 'Entry Level', 'Senior', or empty if none mentioned)
            """
            params = call_ai_fallback(safe_prompt, system_instruction)
            
        if params:
            company = params.get('company', '')
            role = params.get('role', 'Any Role')
            geo = params.get('geography', '')
            chat_setup = params.get('work_setup', '')
            exp = params.get('experience', '')
            
            st.markdown(f"""
            <div class="agent-box">
                <b>🕵️‍♂️ Target Locked:</b><br>
                Company: <b>{company if company else 'Open Market'}</b><br>
                Role: <b>{role}</b> {f"| <i>{exp}</i>" if exp else ""}<br>
                Location: <b>{geo if geo else 'Any'}</b> (Setup: {chat_setup if chat_setup else 'Any'})
            </div>
            """, unsafe_allow_html=True)
            
            jobs = []
            
            do_corporate = False
            do_open = False
            
            if filter_platform == "Corporate Site Only" and company: do_corporate = True
            elif filter_platform == "Open Job Boards Only": do_open = True
            else:
                do_corporate = bool(company)
                do_open = True
                    
            if filter_platform == "Corporate Site Only" and not company:
                st.warning("Selected 'Corporate Site Only' but no company specified. Searching open boards.")
                do_open = True

            if do_corporate:
                with st.spinner(f"🔍 Hunting {company} careers page..."):
                    target_url = find_corporate_url(company, role)
                if target_url:
                    with st.spinner("🤖 Playwright extracting jobs..."):
                        corp_jobs = playwright_scrape_and_parse(target_url, company)
                        if isinstance(corp_jobs, list):
                            for cj in corp_jobs:
                                cj['apply_links'] = [{"site": f"{company} Portal", "url": target_url}]
                                cj['source_tag'] = "🏢 Corporate Site"
                            jobs.extend(corp_jobs)
                else:
                    st.info("No standalone career site found. Deep searching ATS...")

            if do_open:
                with st.spinner("🌐 Scouring open boards (Indeed, Glassdoor, etc.)..."):
                    final_setup = filter_setup if filter_setup != "Any / Optional" else chat_setup
                    
                    loc_parts = []
                    if geo: loc_parts.append(geo)
                    
                    if filter_loc not in ["Any Region / Optional", "Work from Anywhere (Global)"]: 
                        if filter_loc.lower() not in geo.lower(): loc_parts.append(filter_loc)
                    elif filter_loc == "Work from Anywhere (Global)": 
                        loc_parts.append("Worldwide")
                    
                    if filter_state and filter_state != "N/A": loc_parts.append(filter_state.strip())
                    if filter_city and filter_city != "N/A": loc_parts.append(filter_city.strip())
                    
                    loc_query = " ".join(loc_parts).strip()
                    exp_query = exp if exp else ""
                    
                    search_str = f"{company} {role} {exp_query} {final_setup} {loc_query}".replace("Any Role", "").replace("Offline / On-site", "").strip()
                    if "job" not in search_str.lower():
                        search_str += " jobs"
                    
                    query = urllib.parse.quote(search_str)
                    url_serp = f"https://serpapi.com/search.json?engine=google_jobs&q={query}&hl=en&api_key={SERPAPI_KEY}"
                    req_serp = urllib.request.Request(url_serp, headers={'User-Agent': 'Mozilla/5.0'})
                    try:
                        with urllib.request.urlopen(req_serp) as response:
                            data = json.loads(response.read().decode())
                            for j in data.get("jobs_results", []):
                                fetched_company = j.get("company_name", "Unknown")
                                if company and company.lower() not in fetched_company.lower():
                                    continue 
                                
                                raw_job_title = j.get("title", "")
                                if any(spam in raw_job_title.lower() for spam in BANNED_TITLE_WORDS):
                                    continue

                                apply_opts = j.get("apply_options", [])
                                all_links = []
                                
                                if apply_opts:
                                    for opt in apply_opts:
                                        board_name = opt.get("title", "Job Board").replace("Apply on ", "")
                                        is_spam = any(spam in board_name.lower() for spam in BANNED_BOARDS)
                                        if not is_spam:
                                            all_links.append({"site": board_name, "url": opt.get("link", "#")})
                                else:
                                    fallback_url = j.get("share_link", "#")
                                    if not any(spam in fallback_url.lower() for spam in BANNED_BOARDS):
                                        all_links.append({"site": "Direct Link", "url": fallback_url})
                                
                                if not all_links:
                                    continue
                                    
                                jobs.append({
                                    "title": raw_job_title,
                                    "company": fetched_company,
                                    "location": j.get("location", ""),
                                    "type": "Open Board",
                                    "apply_links": all_links,
                                    "source_tag": "🌍 Verified Board"
                                })
                    except: pass

            if do_open:
                ats_targets = [
                    {"name": "LinkedIn", "query": "site:linkedin.com/jobs/view/", "emoji": "🟦"},
                    {"name": "Workday", "query": "site:myworkdayjobs.com", "emoji": "🟧"},
                    {"name": "Greenhouse", "query": "site:boards.greenhouse.io", "emoji": "🟩"},
                    {"name": "WeWorkRemotely", "query": "site:weworkremotely.com", "emoji": "🟪"}
                ]
                
                for ats in ats_targets:
                    with st.spinner(f"🕵️‍♂️ Deep-searching {ats['name']}..."):
                        ats_search_str = f"{ats['query']} {company} {role} {exp_query} {final_setup} {loc_query}".strip()
                        ats_query = urllib.parse.quote(ats_search_str)
                        ats_url = f"https://serpapi.com/search.json?engine=google&q={ats_query}&hl=en&api_key={SERPAPI_KEY}&num=5"
                        
                        req_ats = urllib.request.Request(ats_url, headers={'User-Agent': 'Mozilla/5.0'})
                        try:
                            with urllib.request.urlopen(req_ats) as response:
                                ats_data = json.loads(response.read().decode())
                                for result in ats_data.get("organic_results", []):
                                    title = result.get("title", "")
                                    link = result.get("link", "")
                                    
                                    if company:
                                        norm_target = re.sub(r'[^a-z0-9]', '', company.lower())
                                        norm_title = re.sub(r'[^a-z0-9]', '', title.lower())
                                        if norm_target not in norm_title:
                                            continue
                                    
                                    if any(spam in title.lower() for spam in BANNED_TITLE_WORDS):
                                        continue

                                    if not any(j.get('apply_links') and j['apply_links'][0]['url'] == link for j in jobs):
                                        clean_title = title.replace(" | LinkedIn", "").split(" at ")[0].strip()
                                        if " hiring " in clean_title:
                                            clean_title = clean_title.split(" hiring ")[-1].split(" in ")[0].strip()
                                        clean_title = clean_title.split(" - ")[0].strip()
                                        
                                        jobs.append({
                                            "title": clean_title,
                                            "company": company if company else "Multiple",
                                            "location": geo if geo else "N/A",
                                            "type": "Open Board",
                                            "apply_links": [{"site": f"{ats['name']}", "url": link}],
                                            "source_tag": f"{ats['emoji']} {ats['name']}"
                                        })
                        except: pass

            filtered_jobs = []
            for item in jobs:
                data_string = f"{item.get('type', '')} {item.get('title', '')} {item.get('location', '')}".lower()
                
                if filter_type != "Any / Optional" and filter_type.lower() not in data_string: continue
                if filter_setup != "Any / Optional":
                    if filter_setup == "Remote / WFH":
                        if "remote" not in data_string and "wfh" not in data_string and "work from home" not in data_string and "anywhere" not in data_string: continue
                    elif filter_setup == "Hybrid":
                        if "hybrid" not in data_string: continue
                    elif filter_setup == "Offline / On-site":
                        if "remote" in data_string or "hybrid" in data_string or "wfh" in data_string: continue

                specific_loc_provided = bool(geo) or bool(filter_state and filter_state != "N/A") or bool(filter_city and filter_city != "N/A")
                if filter_loc != "Any Region / Optional":
                    if filter_loc == "Work from Anywhere (Global)":
                        if "anywhere" not in data_string and "worldwide" not in data_string and "global" not in data_string and "remote" not in data_string: continue
                    else:
                        if not specific_loc_provided and filter_loc.lower() not in data_string: 
                            continue

                if filter_state and filter_state != "N/A" and filter_state.strip().lower() not in data_string: continue
                if filter_city and filter_city != "N/A" and filter_city.strip().lower() not in data_string: continue

                filtered_jobs.append(item)

            if not filtered_jobs:
                st.error("No active roles found matching your parameters.")
            else:
                st.success(f"Agent secured {len(filtered_jobs)} strictly verified leads!")
                st.write("") 
                
                for item in filtered_jobs:
                    comp_name = item.get("company", company if company else "Company")
                    encoded_comp = urllib.parse.quote(comp_name)
                    avatar = f"https://ui-avatars.com/api/?name={encoded_comp}&background=random&color=fff&size=128&rounded=true"
                    
                    with st.container(border=True):
                        st.markdown(f"""
                            <div class="job-card">
                                <img src="{avatar}" class="company-logo">
                                <p class="job-title">{item.get('title', 'Role')}</p>
                                <p class="job-subtitle"><b>{comp_name}</b> | 📍 {item.get('location', 'N/A')}</p>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        st.caption(f"{item.get('source_tag', '')} | ⏱️ {item.get('type', 'N/A')}")
                        
                        link_list = item.get('apply_links', [])
                        for idx, link_data in enumerate(link_list):
                            btn_style = "primary" if idx == 0 else "secondary"
                            st.link_button(f"🚀 Apply via {link_data['site']}", link_data['url'], type=btn_style, use_container_width=True)
