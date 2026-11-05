"""Normalize explicit To/Cc/Bcc groups without exposing hidden addresses."""
from email.headerregistry import Address


def groups(recipients, cc=None, bcc=None):
    seen = set()
    result = []
    for values in (recipients, [] if cc is None else cc, [] if bcc is None else bcc):
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError('Destinatários devem ser listas de endereços.')
        if len(values) > 1000:
            raise ValueError('Destinatários acima do limite.')
        clean = []
        for value in values:
            address = value.strip().casefold()
            if not address or any(ord(c) < 32 or c in '<>,;' for c in address):
                raise ValueError('Destinatário inválido.')
            try:
                parsed = Address(addr_spec=address)
                if not parsed.username or not parsed.domain:
                    raise ValueError('Destinatário inválido.')
            except (ValueError, IndexError) as exc:
                raise ValueError('Destinatário inválido.') from exc
            if address not in seen:
                clean.append(address)
                seen.add(address)
        result.append(clean)
    if not result[0] or len(seen) > 1000:
        raise ValueError('Destinatários inválidos ou acima do limite.')
    return tuple(result)
