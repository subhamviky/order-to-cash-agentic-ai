"""Reference data (policies/catalog.yaml): customers, products, accounts."""
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict

import yaml


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    payer_account: str
    credit_limit: Decimal


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: Decimal
    stock: int


class Catalog:
    def __init__(self, path: Path) -> None:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.tenant: str = data["tenant"]
        self.currency: str = data["currency"]
        self.receivable_account: str = data["receivable_account"]
        self.customers: Dict[str, Customer] = {
            cid: Customer(cid, c["name"], c["payer_account"], Decimal(c["credit_limit"]))
            for cid, c in data["customers"].items()}
        self.products: Dict[str, Product] = {
            sku: Product(sku, p["name"], Decimal(p["price"]), int(p["stock"]))
            for sku, p in data["products"].items()}

    def price(self, sku: str, quantity: int) -> Decimal:
        return (self.products[sku].price * quantity).quantize(Decimal("0.01"))
