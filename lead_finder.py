"""
Belgian Websites — Lead Finder Bot 🇧🇪
=======================================
Vindt lokale bedrijven in België die GEEN goede website hebben.
Genereert een lijst met leads + gepersonaliseerde outreach berichten.

Gebruik:
    python lead_finder.py --city "Antwerpen" --type "kapper"
    python lead_finder.py --city "Gent" --type "restaurant" --max 20
    python lead_finder.py --scan-all
"""

import json
import csv
import os
import sys
import re
import time
import random
import argparse
import urllib.request
import urllib.parse
import urllib.error
import ssl
from datetime import datetime
from pathlib import Path

# ============================================================
# Configuration
# ============================================================
CONFIG = {
    "business_name": "Belgian Websites",
    "email": "belgianwebsites@gmail.com",
    "website": "https://belgianwebsites.be",  # Update when hosted

    # Belgian cities to scan
    "cities": [
        "Antwerpen", "Gent", "Brugge", "Leuven", "Mechelen",
        "Hasselt", "Kortrijk", "Oostende", "Aalst", "Sint-Niklaas",
        "Turnhout", "Genk", "Roeselare", "Dendermonde", "Knokke-Heist",
        "Waregem", "Tienen", "Tongeren", "Ieper", "Lokeren"
    ],

    # Business types to target
    "business_types": [
        "kapper", "restaurant", "bakkerij", "slager", "bloemist",
        "tandarts", "fysiotherapeut", "loodgieter", "elektricien",
        "schilder", "fitness", "yogastudio", "cafe", "bar",
        "schoonheidssalon", "nagelstudio", "tattooshop", "fietsenwinkel",
        "autogarage", "dierenarts", "apotheek", "opticien",
        "juwelier", "kledingwinkel", "boekhouder", "advocaat",
        "immobilien", "tuinman", "schoonmaakbedrijf", "traiteur"
    ],

    # Output
    "output_dir": "leads",
    "max_results_per_search": 10,
}

# ============================================================
# Website Checker
# ============================================================
class WebsiteChecker:
    """Checks if a website exists and evaluates its quality."""

    def __init__(self):
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def check_website(self, url):
        """
        Check if a website exists and return quality info.
        Returns dict with: exists, is_mobile_friendly, load_time, has_ssl, score
        """
        if not url or url.strip() == "":
            return {
                "exists": False,
                "url": None,
                "score": 0,
                "issues": ["Geen website gevonden"],
                "opportunity": "HIGH"
            }

        # Clean URL
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        result = {
            "exists": False,
            "url": url,
            "score": 0,
            "issues": [],
            "opportunity": "NONE",
            "load_time": None,
            "has_ssl": url.startswith("https"),
            "is_responsive": None,
        }

        try:
            start_time = time.time()
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            response = urllib.request.urlopen(req, timeout=10, context=self.ctx)
            load_time = time.time() - start_time

            result["exists"] = True
            result["load_time"] = round(load_time, 2)

            html = response.read().decode("utf-8", errors="ignore").lower()

            # Score the website (out of 100)
            score = 100
            issues = []

            # Check SSL
            if not url.startswith("https"):
                score -= 15
                issues.append("❌ Geen HTTPS/SSL")

            # Check load time
            if load_time > 5:
                score -= 20
                issues.append(f"🐌 Trage laadtijd ({load_time:.1f}s)")
            elif load_time > 3:
                score -= 10
                issues.append(f"⚠️ Matige laadtijd ({load_time:.1f}s)")

            # Check mobile responsive
            has_viewport = 'viewport' in html
            if not has_viewport:
                score -= 25
                issues.append("📱 Niet mobiel-vriendelijk")
                result["is_responsive"] = False
            else:
                result["is_responsive"] = True

            # Check modern design indicators
            has_modern_css = any(kw in html for kw in ['flexbox', 'grid', 'tailwind', 'bootstrap', 'font-family'])
            if not has_modern_css:
                score -= 10
                issues.append("🎨 Verouderd design")

            # Check for basic SEO
            has_meta_desc = 'meta' in html and 'description' in html
            has_title = '<title>' in html and '</title>' in html
            if not has_meta_desc:
                score -= 10
                issues.append("🔍 Geen meta description (slecht voor SEO)")
            if not has_title:
                score -= 10
                issues.append("🔍 Geen paginatitel")

            # Check if it's just a Facebook page or placeholder
            is_placeholder = any(kw in html for kw in [
                'coming soon', 'under construction', 'binnenkort',
                'in opbouw', 'website in aanbouw'
            ])
            if is_placeholder:
                score -= 30
                issues.append("🚧 Website is 'in opbouw' / placeholder")

            is_facebook_only = 'facebook.com' in url
            if is_facebook_only:
                score -= 40
                issues.append("📘 Alleen een Facebook-pagina, geen echte website")

            result["score"] = max(0, score)
            result["issues"] = issues

            # Determine opportunity level
            if score < 30:
                result["opportunity"] = "HIGH"
            elif score < 60:
                result["opportunity"] = "MEDIUM"
            elif score < 80:
                result["opportunity"] = "LOW"
            else:
                result["opportunity"] = "NONE"

        except urllib.error.HTTPError as e:
            result["issues"] = [f"❌ Website geeft foutcode: {e.code}"]
            result["opportunity"] = "HIGH"
        except urllib.error.URLError:
            result["issues"] = ["❌ Website is niet bereikbaar"]
            result["opportunity"] = "HIGH"
        except Exception as e:
            result["issues"] = [f"❌ Fout bij checken: {str(e)[:50]}"]
            result["opportunity"] = "MEDIUM"

        return result


# ============================================================
# Lead Manager
# ============================================================
class LeadManager:
    """Manages leads: storage, deduplication, export."""

    def __init__(self, output_dir="leads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.leads_file = self.output_dir / "all_leads.json"
        self.leads = self._load_leads()

    def _load_leads(self):
        if self.leads_file.exists():
            with open(self.leads_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_leads(self):
        with open(self.leads_file, "w", encoding="utf-8") as f:
            json.dump(self.leads, f, indent=2, ensure_ascii=False)

    def add_lead(self, lead):
        """Add a lead if not duplicate."""
        # Check for duplicates by name + city
        for existing in self.leads:
            if (existing.get("name", "").lower() == lead.get("name", "").lower() and
                existing.get("city", "").lower() == lead.get("city", "").lower()):
                return False  # Duplicate

        lead["added_date"] = datetime.now().isoformat()
        lead["status"] = "new"
        self.leads.append(lead)
        self._save_leads()
        return True

    def get_leads(self, opportunity=None, city=None, status=None):
        """Filter leads."""
        results = self.leads
        if opportunity:
            results = [l for l in results if l.get("opportunity") == opportunity]
        if city:
            results = [l for l in results if l.get("city", "").lower() == city.lower()]
        if status:
            results = [l for l in results if l.get("status") == status]
        return results

    def export_csv(self, filename=None):
        """Export leads to CSV."""
        if not filename:
            filename = self.output_dir / f"leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

        if not self.leads:
            print("❌ Geen leads om te exporteren.")
            return

        fields = ["name", "type", "city", "website", "opportunity",
                  "score", "issues", "status", "added_date"]

        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for lead in self.leads:
                row = {**lead}
                row["issues"] = " | ".join(lead.get("issues", []))
                writer.writerow(row)

        print(f"✅ Leads geëxporteerd naar: {filename}")
        return filename


# ============================================================
# Outreach Message Generator
# ============================================================
class OutreachGenerator:
    """Generates personalized outreach messages."""

    TEMPLATES = {
        "no_website": {
            "subject": "Website voor {name}? 🚀",
            "message": """Beste {name},

Ik kwam {name} tegen in {city} en merkte op dat jullie nog geen website hebben. 
In 2026 zoekt meer dan 80% van de klanten online voordat ze een lokaal bedrijf bezoeken.

Bij Belgian Websites bouwen we professionele, moderne websites speciaal voor lokale bedrijven zoals die van jullie.

✅ Volledig op maat gemaakt
✅ Mobiel-vriendelijk
✅ Klaar binnen 7 dagen
✅ Vanaf €249

Zullen we eens vrijblijvend bespreken wat een website voor {name} kan betekenen?

Groeten,
Belgian Websites
belgianwebsites@gmail.com"""
        },

        "bad_website": {
            "subject": "Kleine tip voor de website van {name} 💡",
            "message": """Beste {name},

Ik bekeek de website van {name} ({website}) en zag een paar verbeterpunten:

{issues_list}

Een moderne, snelle website kan een groot verschil maken voor jullie online vindbaarheid en klantenaantal.

Bij Belgian Websites helpen we lokale bedrijven in {city} met het verbeteren of opnieuw bouwen van hun website.

Wil je weten wat we voor {name} kunnen doen? Ik maak graag een gratis analyse!

Groeten,
Belgian Websites
belgianwebsites@gmail.com"""
        },

        "placeholder_website": {
            "subject": "Hulp met de website van {name}? 🛠️",
            "message": """Beste {name},

Ik zag dat de website van {name} momenteel nog in aanbouw is. 
Mocht je hulp nodig hebben om die snel af te ronden, dan kan ik je helpen!

Bij Belgian Websites bouwen we complete websites voor lokale bedrijven in {city}:
- Professioneel design op maat
- Klaar binnen 7 dagen
- Alles geregeld (design, hosting, SEO)

Interesse in een vrijblijvend gesprek?

Groeten,
Belgian Websites
belgianwebsites@gmail.com"""
        },

        "instagram_dm": {
            "subject": None,
            "message": """Hey {name}! 👋

Ik zag jullie profiel en het ziet er goed uit! 🔥
Maar ik merkte dat jullie nog geen website hebben.

Wist je dat 80% van de klanten eerst online zoekt? Een professionele website kan jullie echt helpen meer klanten te krijgen.

Ik bouw websites speciaal voor lokale bedrijven in {city}, vanaf €249. 
Check belgianwebsites.be voor voorbeelden!

Interesse? Stuur gerust een berichtje! 😊"""
        }
    }

    @classmethod
    def generate(cls, lead, template_key=None):
        """Generate a personalized outreach message for a lead."""
        # Auto-select template
        if not template_key:
            opp = lead.get("opportunity", "NONE")
            has_website = lead.get("website") and lead["website"] != ""

            if not has_website or opp == "HIGH":
                # Check if it's a placeholder
                issues = lead.get("issues", [])
                if any("opbouw" in str(i).lower() or "placeholder" in str(i).lower() for i in issues):
                    template_key = "placeholder_website"
                elif has_website:
                    template_key = "bad_website"
                else:
                    template_key = "no_website"
            elif opp == "MEDIUM":
                template_key = "bad_website"
            else:
                return None  # No need to reach out

        template = cls.TEMPLATES.get(template_key)
        if not template:
            return None

        # Format issues list
        issues_list = ""
        if lead.get("issues"):
            issues_list = "\n".join(f"  • {issue}" for issue in lead["issues"])

        # Generate message
        result = {
            "subject": template["subject"].format(**lead) if template["subject"] else None,
            "message": template["message"].format(
                name=lead.get("name", ""),
                city=lead.get("city", ""),
                website=lead.get("website", ""),
                issues_list=issues_list,
                **{k: v for k, v in lead.items() if k not in ["name", "city", "website", "issues_list"]}
            ),
            "template_used": template_key
        }

        return result


# ============================================================
# Search Engine (Google Search scraper)
# ============================================================
class BusinessSearcher:
    """Searches for local businesses using web search."""

    def __init__(self):
        self.checker = WebsiteChecker()
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def search_businesses(self, business_type, city, max_results=10):
        """
        Search for businesses of a given type in a city.
        Returns a list of business dicts.
        """
        query = f"{business_type} {city} België"
        print(f"\n🔍 Zoeken: '{query}'...")

        businesses = []

        try:
            # Use DuckDuckGo HTML search (no API key needed)
            encoded_query = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })

            response = urllib.request.urlopen(req, timeout=15, context=self.ctx)
            html = response.read().decode("utf-8", errors="ignore")

            # Parse results (basic regex parsing)
            # Find result blocks
            results = re.findall(
                r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:td|div)',
                html, re.DOTALL
            )

            for url_match, title_html, snippet_html in results[:max_results]:
                # Clean HTML tags
                title = re.sub(r'<[^>]+>', '', title_html).strip()
                snippet = re.sub(r'<[^>]+>', '', snippet_html).strip()

                # Extract actual URL from DuckDuckGo redirect
                actual_url = url_match
                if 'uddg=' in actual_url:
                    url_param = re.search(r'uddg=([^&]+)', actual_url)
                    if url_param:
                        actual_url = urllib.parse.unquote(url_param.group(1))

                # Skip irrelevant results
                skip_domains = ['facebook.com', 'instagram.com', 'yelp.com',
                                'tripadvisor.', 'linkedin.com', 'twitter.com',
                                'youtube.com', 'goudengids.be', 'pagesdor.be']

                is_directory = any(d in actual_url.lower() for d in skip_domains)

                business = {
                    "name": title[:80],
                    "type": business_type,
                    "city": city,
                    "website": actual_url if not is_directory else "",
                    "snippet": snippet[:200],
                    "source": "duckduckgo",
                    "is_directory_listing": is_directory,
                }

                businesses.append(business)

            # Small delay to be respectful
            time.sleep(random.uniform(1, 3))

        except Exception as e:
            print(f"   ⚠️ Zoekfout: {e}")

        print(f"   📋 {len(businesses)} resultaten gevonden")
        return businesses

    def analyze_business(self, business):
        """Check the business's website and add quality data."""
        website = business.get("website", "")

        if business.get("is_directory_listing"):
            # Business found on directory but has no own website
            business["website"] = ""
            website_data = self.checker.check_website("")
        else:
            website_data = self.checker.check_website(website)

        business.update({
            "score": website_data["score"],
            "issues": website_data["issues"],
            "opportunity": website_data["opportunity"],
            "load_time": website_data.get("load_time"),
            "is_responsive": website_data.get("is_responsive"),
        })

        return business


# ============================================================
# Main Bot
# ============================================================
class BelgianWebsitesBot:
    """Main bot that orchestrates searching, checking, and outreach."""

    def __init__(self):
        self.searcher = BusinessSearcher()
        self.leads = LeadManager(
            output_dir=str(Path(__file__).parent / CONFIG["output_dir"])
        )
        self.outreach = OutreachGenerator()

    def scan(self, city, business_type, max_results=10):
        """Scan a city for businesses of a certain type."""
        print(f"\n{'='*60}")
        print(f"🇧🇪 BELGIAN WEBSITES — Lead Scanner")
        print(f"{'='*60}")
        print(f"📍 Stad: {city}")
        print(f"🏪 Type: {business_type}")
        print(f"{'='*60}")

        # Search for businesses
        businesses = self.searcher.search_businesses(business_type, city, max_results)

        if not businesses:
            print("❌ Geen bedrijven gevonden.")
            return []

        # Analyze each business
        leads_found = []
        for i, biz in enumerate(businesses):
            print(f"\n📊 [{i+1}/{len(businesses)}] Analyseren: {biz['name'][:50]}...")

            analyzed = self.searcher.analyze_business(biz)

            # Only save leads with opportunity
            if analyzed["opportunity"] != "NONE":
                added = self.leads.add_lead(analyzed)
                if added:
                    leads_found.append(analyzed)
                    emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(analyzed["opportunity"], "⚪")
                    print(f"   {emoji} Opportunity: {analyzed['opportunity']} (score: {analyzed['score']}/100)")
                    for issue in analyzed.get("issues", []):
                        print(f"      {issue}")
                else:
                    print(f"   ⏭️  Al in database")
            else:
                print(f"   ✅ Website is goed (score: {analyzed['score']}/100)")

            # Be nice to servers
            time.sleep(random.uniform(0.5, 1.5))

        # Summary
        print(f"\n{'='*60}")
        print(f"📊 SAMENVATTING")
        print(f"{'='*60}")
        print(f"   Bedrijven gevonden: {len(businesses)}")
        print(f"   Nieuwe leads:       {len(leads_found)}")
        high = len([l for l in leads_found if l["opportunity"] == "HIGH"])
        medium = len([l for l in leads_found if l["opportunity"] == "MEDIUM"])
        print(f"   🔴 Hoge kans:       {high}")
        print(f"   🟡 Medium kans:     {medium}")
        print(f"   Totaal in database: {len(self.leads.leads)}")
        print(f"{'='*60}")

        return leads_found

    def scan_all(self, cities=None, types=None, max_per_search=5):
        """Scan multiple cities and business types."""
        cities = cities or CONFIG["cities"][:5]  # Start with 5 cities
        types = types or CONFIG["business_types"][:5]  # Start with 5 types

        total_leads = 0
        for city in cities:
            for btype in types:
                leads = self.scan(city, btype, max_per_search)
                total_leads += len(leads)
                # Longer delay between searches
                time.sleep(random.uniform(2, 5))

        print(f"\n🎉 KLAAR! Totaal nieuwe leads gevonden: {total_leads}")
        print(f"📁 Totaal in database: {len(self.leads.leads)}")

    def generate_outreach(self, limit=None):
        """Generate outreach messages for all new leads."""
        new_leads = self.leads.get_leads(status="new")
        if limit:
            new_leads = new_leads[:limit]

        if not new_leads:
            print("❌ Geen nieuwe leads om te contacteren.")
            return

        outreach_dir = Path(self.leads.output_dir) / "outreach"
        outreach_dir.mkdir(exist_ok=True)

        messages = []
        for lead in new_leads:
            msg = OutreachGenerator.generate(lead)
            if msg:
                messages.append({
                    "lead": lead["name"],
                    "city": lead.get("city", ""),
                    "opportunity": lead["opportunity"],
                    **msg
                })

        # Save outreach messages
        outreach_file = outreach_dir / f"outreach_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(outreach_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2, ensure_ascii=False)

        # Also print them
        print(f"\n{'='*60}")
        print(f"📧 OUTREACH BERICHTEN ({len(messages)} stuks)")
        print(f"{'='*60}")

        for i, msg in enumerate(messages):
            emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(msg["opportunity"], "⚪")
            print(f"\n{'─'*50}")
            print(f"{emoji} [{i+1}] {msg['lead']} ({msg['city']})")
            if msg.get("subject"):
                print(f"📌 Onderwerp: {msg['subject']}")
            print(f"{'─'*50}")
            print(msg["message"])

        print(f"\n✅ Berichten opgeslagen in: {outreach_file}")
        return messages

    def export(self):
        """Export all leads to CSV."""
        return self.leads.export_csv()

    def dashboard(self):
        """Show a quick overview of all leads."""
        leads = self.leads.leads

        if not leads:
            print("📭 Nog geen leads. Start een scan met: python lead_finder.py --city Antwerpen --type kapper")
            return

        print(f"\n{'='*60}")
        print(f"🇧🇪 BELGIAN WEBSITES — Dashboard")
        print(f"{'='*60}")
        print(f"   📊 Totaal leads:  {len(leads)}")

        # By opportunity
        high = len([l for l in leads if l.get("opportunity") == "HIGH"])
        medium = len([l for l in leads if l.get("opportunity") == "MEDIUM"])
        low = len([l for l in leads if l.get("opportunity") == "LOW"])
        print(f"   🔴 Hoge kans:     {high}")
        print(f"   🟡 Medium kans:   {medium}")
        print(f"   🟢 Lage kans:     {low}")

        # By status
        new = len([l for l in leads if l.get("status") == "new"])
        contacted = len([l for l in leads if l.get("status") == "contacted"])
        print(f"\n   📬 Nieuw:         {new}")
        print(f"   📨 Gecontacteerd: {contacted}")

        # By city
        cities = {}
        for l in leads:
            c = l.get("city", "Onbekend")
            cities[c] = cities.get(c, 0) + 1

        print(f"\n   📍 Per stad:")
        for city, count in sorted(cities.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"      {city}: {count}")

        # Top leads
        hot_leads = [l for l in leads if l.get("opportunity") == "HIGH" and l.get("status") == "new"]
        if hot_leads:
            print(f"\n   🔥 Top leads (geen website):")
            for lead in hot_leads[:10]:
                print(f"      • {lead['name']} ({lead.get('city', '?')}) — {lead.get('type', '?')}")

        print(f"{'='*60}")


# ============================================================
# CLI Entry Point
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="🇧🇪 Belgian Websites — Lead Finder Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  python lead_finder.py --city Antwerpen --type kapper
  python lead_finder.py --city Gent --type restaurant --max 20
  python lead_finder.py --scan-all
  python lead_finder.py --outreach
  python lead_finder.py --export
  python lead_finder.py --dashboard
        """
    )

    parser.add_argument("--city", type=str, help="Stad om te scannen")
    parser.add_argument("--type", type=str, help="Type bedrijf (bijv. kapper, restaurant)")
    parser.add_argument("--max", type=int, default=10, help="Max resultaten per zoekopdracht")
    parser.add_argument("--scan-all", action="store_true", help="Scan meerdere steden en types")
    parser.add_argument("--outreach", action="store_true", help="Genereer outreach berichten")
    parser.add_argument("--export", action="store_true", help="Exporteer leads naar CSV")
    parser.add_argument("--dashboard", action="store_true", help="Toon dashboard overzicht")
    parser.add_argument("--check", type=str, help="Check één specifieke website URL")

    args = parser.parse_args()
    bot = BelgianWebsitesBot()

    if args.check:
        # Quick single website check
        checker = WebsiteChecker()
        result = checker.check_website(args.check)
        print(f"\n🔍 Website Check: {args.check}")
        print(f"   Score: {result['score']}/100")
        print(f"   Opportunity: {result['opportunity']}")
        if result["issues"]:
            print("   Problemen:")
            for issue in result["issues"]:
                print(f"     {issue}")
        else:
            print("   ✅ Geen problemen gevonden!")

    elif args.dashboard:
        bot.dashboard()

    elif args.export:
        bot.export()

    elif args.outreach:
        bot.generate_outreach()

    elif args.scan_all:
        bot.scan_all()

    elif args.city and args.type:
        bot.scan(args.city, args.type, args.max)
        # Auto generate outreach for new leads
        print("\n📧 Outreach berichten genereren...")
        bot.generate_outreach(limit=5)
        # Auto export
        bot.export()

    else:
        parser.print_help()
        print("\n💡 Quick start: python lead_finder.py --city Antwerpen --type kapper")


if __name__ == "__main__":
    main()
