"""Plain text tables; no terminal capabilities required."""
import json


def table(headers, rows):
    rows = [[str(value) if value is not None else "-" for value in row] for row in rows]
    if not rows:
        return "No entries."
    # Avoid control sequences from installed metadata or display names.
    clean = lambda value: "".join(c if ord(c) >= 32 and ord(c) != 127 else "?" for c in value)[:128]
    rows = [[clean(v) for v in row] for row in rows]
    widths = [min(64, max(len(headers[i]), *(len(row[i]) for row in rows))) for i in range(len(headers))]
    def render(row):
        return " | ".join(v[:width].ljust(width) for v, width in zip(row, widths)).rstrip()
    return "\n".join([render(headers), "-+-".join("-" * width for width in widths), *(render(row) for row in rows)])


def structured(command, data):
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if command == "status" and isinstance(data, dict):
        keys = ("name", "map", "mode", "phase", "players", "max_players", "anti_cheat", "anti_cheat_active", "max_ping", "votes", "password_required", "block_vpn")
        return table(["Status", "Value"], [[key, data[key]] for key in keys if key in data])
    if command == "players":
        players = data.get("players") if isinstance(data, dict) else data
        if isinstance(players, list):
            return table(["#", "Name", "Team", "Score", "K/D", "Ping", "Player ID"], [
                [p.get("number"), p.get("name"), p.get("team"), p.get("score"),
                 f"{p.get('kills', '-')}/{p.get('deaths', '-')}", p.get("ping"), p.get("id", p.get("player_id"))]
                for p in players if isinstance(p, dict)])
    if command in ("maps", "modes") and isinstance(data, dict) and isinstance(data.get("entries"), list):
        return table(["Name", "Reference", "Kind"], [[p.get("name"), p.get("reference"), p.get("kind")] for p in data["entries"] if isinstance(p, dict)])
    return json.dumps(data, indent=2, ensure_ascii=False) if data is not None else None
