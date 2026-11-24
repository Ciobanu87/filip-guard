"""Public catalog/product observations only; no cart, checkout or order actions."""
from decimal import Decimal,InvalidOperation
from bs4 import BeautifulSoup
from guard_module_contract import Check


def run(context,config):
    for path in config['paths']:
        url=context.origin+path
        seen=False
        try:
            status,kind,body=context.site(path)
            seen=True
            if status!=200:
                yield Check('commerce','catalog-http',url,'fail','Catalog/product page returned an unexpected HTTP status.',
                    'Review the public route and server response; do not place an order to test it.','High',(('http_status',status),));continue
            yield Check('commerce','catalog-http',url,'pass','Catalog/product route is reachable.','No action required.',evidence=(('http_status',status),))
            if not config['require_product']:continue
            if kind not in ('text/html','application/xhtml+xml'):raise ValueError('Expected product HTML')
            soup=BeautifulSoup(body,'html.parser');products=[]
            def walk(value,depth=0):
                if depth>6:return
                if isinstance(value,list):
                    for item in value[:100]:walk(item,depth+1)
                elif isinstance(value,dict):
                    types=value.get('@type',[]);types=[types] if type(types) is str else types
                    if isinstance(types,list) and 'Product' in types:products.append(value)
                    if '@graph' in value:walk(value['@graph'],depth+1)
            for script in soup.select('script[type="application/ld+json"]')[:10]:
                raw=script.string or script.get_text()
                if len(raw)>100000:raise ValueError('Product metadata too large')
                walk(context.json(raw.encode()))
            if not products:
                yield Check('commerce','product-data',url,'fail','Expected Product structured data was not observed.',
                    'Inspect the product template and published JSON-LD. This does not prove checkout is broken.');continue
            errors=[];offers=[]
            for product in products[:10]:
                offered=product.get('offers',[]);offered=[offered] if type(offered) is dict else offered
                if type(offered) is list:offers.extend(offered[:10])
            for offer in offers:
                if type(offer) is not dict:errors.append('invalid-offer');continue
                try:
                    price=Decimal(str(offer.get('price','')))
                    if not price.is_finite() or price<0:raise InvalidOperation()
                except (InvalidOperation,ValueError):errors.append('invalid-price')
                currency=offer.get('priceCurrency')
                if config['expected_currency'] and currency!=config['expected_currency']:errors.append('currency-mismatch')
            if not offers:errors.append('offer-unavailable')
            yield Check('commerce','product-data',url,'fail' if errors else 'pass',
                'Product offer metadata requires review.' if errors else 'Observed product offer metadata meets configured checks.',
                'Compare the published offer with the real catalog; verify price/currency manually before changes.',
                evidence=tuple(('condition',code) for code in sorted(set(errors))))
        except Exception:
            yield Check('commerce','product-data' if seen else 'catalog-http',url,'unknown','Commerce check could not be completed.',
                'Check reachability, TLS and request limits; prior product issues remain unverified.')
