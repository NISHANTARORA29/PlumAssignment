"""
Comprehensive Test Runner with Detailed Output
Run this to validate all test cases
"""
import json
from adjudication_engine import ClaimAdjudicator
from datetime import datetime
import sys


def load_test_cases():
    """Load test cases from JSON file"""
    try:
        with open("test_cases.json", 'r') as f:
            data = json.load(f)
            return data["test_cases"]
    except FileNotFoundError:
        print("❌ test_cases.json not found!")
        print("Please ensure test_cases.json is in the same directory")
        sys.exit(1)


def run_test_case(test_case, adjudicator):
    """Run a single test case and return results"""
    case_id = test_case["case_id"]
    input_data = test_case["input_data"]
    expected = test_case["expected_output"]
    
    # Convert input to claim_data format
    claim_data = {
        "prescription": input_data.get("documents", {}).get("prescription", {}),
        "bill": input_data.get("documents", {}).get("bill", {}),
        "test_reports": []
    }
    
    # Member info
    member_info = {
        "member_id": input_data.get("member_id"),
        "member_name": input_data.get("member_name"),
        "treatment_date": input_data.get("treatment_date"),
        "claim_amount": input_data.get("claim_amount"),
        "member_join_date": input_data.get("member_join_date", "2024-01-01"),
        "previous_claims_ytd": 0,
        "previous_claims_same_day": input_data.get("previous_claims_same_day", 0),
        "hospital": input_data.get("hospital"),
        "cashless_request": input_data.get("cashless_request", False),
        "preauth_obtained": input_data.get("preauth_obtained", False)
    }
    
    # Run adjudication
    try:
        decision = adjudicator.adjudicate_claim(claim_data, member_info)
        error = None
    except Exception as e:
        decision = None
        error = str(e)
    
    return {
        "test_case": test_case,
        "decision": decision,
        "expected": expected,
        "error": error
    }


def validate_result(decision, expected):
    """Validate if decision matches expected output"""
    if not decision:
        return False, ["System error occurred"]
    
    issues = []
    
    # Check decision type
    if decision["decision"] != expected.get("decision"):
        issues.append(f"Decision mismatch: expected {expected.get('decision')}, got {decision['decision']}")
    
    # Check approved amount
    if expected.get("approved_amount") is not None:
        expected_amt = expected["approved_amount"]
        actual_amt = decision["approved_amount"]
        
        # Allow 10% tolerance
        tolerance = max(expected_amt * 0.1, 100)
        diff = abs(actual_amt - expected_amt)
        
        if diff > tolerance:
            issues.append(f"Amount mismatch: expected ₹{expected_amt}, got ₹{actual_amt} (diff: ₹{diff:.2f})")
    
    # Check rejection reasons
    if expected.get("rejection_reasons"):
        expected_reasons = set(expected["rejection_reasons"])
        actual_reasons = set(decision.get("rejection_reasons", []))
        
        if not expected_reasons.intersection(actual_reasons):
            issues.append(f"Rejection reasons mismatch: expected {expected_reasons}, got {actual_reasons}")
    
    return len(issues) == 0, issues


def print_test_header(case_num, total, test_case):
    """Print formatted test header"""
    print("\n" + "=" * 100)
    print(f"TEST {case_num}/{total}: {test_case['case_name']} [{test_case['case_id']}]")
    print("=" * 100)
    print(f"📝 {test_case['description']}")
    print("-" * 100)


def print_test_inputs(test_case):
    """Print test inputs"""
    input_data = test_case["input_data"]
    print("\n📥 INPUT:")
    print(f"   Member: {input_data.get('member_name')} ({input_data.get('member_id')})")
    print(f"   Treatment Date: {input_data.get('treatment_date')}")
    print(f"   Claim Amount: ₹{input_data.get('claim_amount')}")
    
    docs = input_data.get("documents", {})
    if docs.get("prescription"):
        rx = docs["prescription"]
        print(f"   Diagnosis: {rx.get('diagnosis', 'N/A')}")
        print(f"   Doctor: {rx.get('doctor_name', 'N/A')} (Reg: {rx.get('doctor_reg', 'N/A')})")


def print_comparison(decision, expected):
    """Print expected vs actual comparison"""
    print("\n📊 COMPARISON:")
    print(f"   Expected Decision: {expected.get('decision')}")
    print(f"   Actual Decision:   {decision['decision']}")
    
    if expected.get("approved_amount") is not None:
        print(f"   Expected Amount:   ₹{expected['approved_amount']}")
        print(f"   Actual Amount:     ₹{decision['approved_amount']}")
        
        if decision.get('deductions'):
            deductions = decision['deductions']
            if deductions.get('copay', 0) > 0:
                print(f"   Copay Deduction:   ₹{deductions['copay']}")
            if deductions.get('discount', 0) > 0:
                print(f"   Network Discount:  ₹{deductions['discount']}")
    
    if expected.get("rejection_reasons"):
        print(f"   Expected Reasons:  {', '.join(expected['rejection_reasons'])}")
        if decision.get("rejection_reasons"):
            print(f"   Actual Reasons:    {', '.join(decision['rejection_reasons'])}")
    
    if expected.get("flags"):
        print(f"   Expected Flags:    {', '.join(expected['flags'])}")
        if decision.get("flags"):
            print(f"   Actual Flags:      {', '.join(decision['flags'])}")
    
    if decision.get("rejected_items"):
        print(f"   Rejected Items:    {', '.join(decision['rejected_items'])}")
    
    if decision.get("notes"):
        print(f"   Notes: {decision['notes']}")
    
    print(f"   Confidence: {decision.get('confidence_score', 0):.2f}")


def print_result(passed, issues):
    """Print test result"""
    if passed:
        print("\n✅ TEST PASSED")
    else:
        print("\n❌ TEST FAILED")
        print("\n⚠️  Issues:")
        for issue in issues:
            print(f"   • {issue}")


def print_summary(results):
    """Print overall summary"""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    
    print("\n" + "=" * 100)
    print("📊 TEST EXECUTION SUMMARY")
    print("=" * 100)
    print(f"\n   Total Tests:  {total}")
    print(f"   ✅ Passed:     {passed} ({passed/total*100:.1f}%)")
    print(f"   ❌ Failed:     {failed} ({failed/total*100:.1f}%)")
    
    if failed > 0:
        print(f"\n   Failed Tests:")
        for r in results:
            if not r["passed"]:
                print(f"      • {r['test_case']['case_id']}: {r['test_case']['case_name']}")
    
    print("\n" + "=" * 100)


def main():
    """Main test execution"""
    print("\n" + "🏥" * 50)
    print("OPD CLAIM ADJUDICATION SYSTEM - COMPREHENSIVE TEST SUITE")
    print("🏥" * 50)
    
    # Load test cases
    test_cases = load_test_cases()
    print(f"\n✓ Loaded {len(test_cases)} test cases")
    
    # Initialize adjudicator
    adjudicator = ClaimAdjudicator()
    print("✓ Adjudication engine initialized")
    
    # Run tests
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        # Print test header
        print_test_header(i, len(test_cases), test_case)
        
        # Print inputs
        print_test_inputs(test_case)
        
        # Run test
        result = run_test_case(test_case, adjudicator)
        
        # Validate
        if result["error"]:
            passed = False
            issues = [f"System Error: {result['error']}"]
        else:
            passed, issues = validate_result(result["decision"], result["expected"])
        
        # Print comparison
        if result["decision"]:
            print_comparison(result["decision"], result["expected"])
        
        # Print result
        print_result(passed, issues)
        
        # Store result
        results.append({
            "test_case": test_case,
            "passed": passed,
            "issues": issues
        })
    
    # Print summary
    print_summary(results)
    
    # Save detailed report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "results": [{
            "case_id": r["test_case"]["case_id"],
            "case_name": r["test_case"]["case_name"],
            "passed": r["passed"],
            "issues": r["issues"]
        } for r in results]
    }
    
    with open("test_report.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 Detailed report saved to: test_report.json\n")
    
    # Exit with appropriate code
    sys.exit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()