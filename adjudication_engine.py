"""
Claim Adjudication Engine - FIXED VERSION v2
Main logic for approving/rejecting claims
"""
from datetime import datetime
from document_processor import validate_doctor_registration, check_document_completeness
from policy_validator import PolicyValidator


class ClaimAdjudicator:
    def __init__(self, policy_path="policy_terms.json"):
        self.policy_validator = PolicyValidator(policy_path)
        
    def adjudicate_claim(self, claim_data, member_info=None):
        """
        Main adjudication function - evaluates claim and makes decision
        
        Args:
            claim_data: Structured data from documents
            member_info: Additional member information (join_date, previous_claims, etc.)
            
        Returns:
            dict: Adjudication decision with reasoning
        """
        decision = {
            "claim_id": f"CLM_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "decision": "PENDING",
            "approved_amount": 0,
            "rejection_reasons": [],
            "flags": [],
            "confidence_score": 0.0,
            "notes": "",
            "deductions": {},
            "next_steps": ""
        }
        
        # Step 1: Document Validation
        doc_check = self._validate_documents(claim_data)
        if not doc_check["valid"]:
            decision["decision"] = "REJECTED"
            decision["rejection_reasons"] = doc_check["reasons"]
            decision["confidence_score"] = 1.0
            decision["notes"] = "Document validation failed"
            return decision
        
        # Extract key information
        prescription = claim_data.get("prescription", {}) or {}
        bill = claim_data.get("bill", {}) or {}
        
        member_id = member_info.get("member_id") if member_info else None
        member_name = member_info.get("member_name") if member_info else prescription.get("patient_name")
        treatment_date = member_info.get("treatment_date") if member_info else prescription.get("treatment_date")
        claim_amount = member_info.get("claim_amount") if member_info else bill.get("total_amount", 0)
        
        # Step 2: Eligibility Check
        eligibility = self.policy_validator.check_member_eligibility(member_id, treatment_date)
        if not eligibility["eligible"]:
            decision["decision"] = "REJECTED"
            decision["rejection_reasons"].append(eligibility["reason"])
            decision["confidence_score"] = 0.98
            decision["notes"] = "Member eligibility check failed"
            return decision
        
        # Step 3: Waiting Period Check
        if member_info and member_info.get("member_join_date"):
            diagnosis = prescription.get("diagnosis", "")
            waiting_check = self.policy_validator.check_waiting_period(
                member_info["member_join_date"],
                treatment_date,
                diagnosis
            )
            if not waiting_check["satisfied"]:
                decision["decision"] = "REJECTED"
                decision["rejection_reasons"].append("WAITING_PERIOD")
                decision["confidence_score"] = 0.96
                decision["notes"] = f"{waiting_check.get('condition', 'Treatment')} has waiting period. Eligible from {waiting_check.get('eligible_date')}"
                return decision
        
        # Step 4: Coverage Verification (check exclusions FIRST)
        diagnosis = prescription.get("diagnosis", "")
        treatments = prescription.get("procedures", []) or prescription.get("treatment", [])
        if isinstance(treatments, str):
            treatments = [treatments]
        medicines = prescription.get("medicines_prescribed", [])
        tests = prescription.get("tests_prescribed", []) or bill.get("test_names", [])
        
        coverage_check = self.policy_validator.check_coverage(diagnosis, treatments, medicines)
        category = coverage_check["category"]
        
        # Check for FULLY excluded treatments (reject immediately)
        if not coverage_check["covered"] and not coverage_check["partial_coverage"]:
            decision["decision"] = "REJECTED"
            decision["rejection_reasons"].append("SERVICE_NOT_COVERED")
            decision["confidence_score"] = 0.97
            decision["notes"] = f"Treatment/service not covered under policy: {', '.join(coverage_check['excluded_items'])}"
            return decision
        
        # Step 5: Calculate approved amount EARLY (before fraud/preauth/limits)
        # This is the KEY FIX - we need to know the actual claimable amount early
        approved_claim_amount = claim_amount
        excluded_amount = 0
        
        if coverage_check["excluded_items"]:
            # Calculate excluded amount
            excluded_amount = self._calculate_excluded_amount(bill, coverage_check["excluded_items"])
            approved_claim_amount = claim_amount - excluded_amount
            decision["decision"] = "PARTIAL"
            decision["rejected_items"] = coverage_check["excluded_items"]
            decision["flags"].append("Contains excluded items")
        
        # Step 6: Fraud Detection
        fraud_score = self._check_fraud_indicators(claim_data, member_info)
        if fraud_score > 0.5:
            decision["decision"] = "MANUAL_REVIEW"
            if member_info and member_info.get("previous_claims_same_day", 0) >= 2:
                decision["flags"].append("Multiple claims same day")
            decision["flags"].append("Unusual pattern detected")
            decision["confidence_score"] = 0.65
            decision["notes"] = "Flagged for manual review due to unusual patterns"
            return decision
        
        # Step 7: Pre-authorization Check (check on approved amount)
        if self.policy_validator.requires_preauth(treatments, tests):
            if not member_info or not member_info.get("preauth_obtained"):
                # Only reject if APPROVED claim amount is high value
                if approved_claim_amount > 10000:
                    decision["decision"] = "REJECTED"
                    decision["rejection_reasons"].append("PRE_AUTH_MISSING")
                    decision["confidence_score"] = 0.94
                    decision["notes"] = "Pre-authorization required for MRI/CT scans above ₹10000"
                    return decision
        
        # Step 8: Limit Validation (check on APPROVED amount after exclusions)
        previous_claims = member_info.get("previous_claims_ytd", 0) if member_info else 0
        
        limit_check = self.policy_validator.check_limits(approved_claim_amount, category, previous_claims)
        
        if not limit_check["within_limits"]:
            decision["decision"] = "REJECTED"
            decision["rejection_reasons"].append(limit_check["limit_type"])
            decision["confidence_score"] = 0.98
            if excluded_amount > 0:
                decision["notes"] = f"Even after excluding ₹{excluded_amount}, remaining claim exceeds {limit_check['limit_type']}. Max allowed: ₹{limit_check['max_allowed']}"
            else:
                decision["notes"] = f"Claim exceeds {limit_check['limit_type']}. Max allowed: ₹{limit_check['max_allowed']}"
            return decision
        
        # Step 9: Calculate Final Amount
        hospital_name = bill.get("hospital_name") or member_info.get("hospital")
        is_network = self._is_network_hospital(hospital_name)
        copay_calc = self.policy_validator.calculate_copay(approved_claim_amount, category, is_network)
        
        decision["approved_amount"] = copay_calc["net_payable"]
        decision["deductions"] = {
            "copay": copay_calc["copay_amount"],
            "discount": copay_calc["discount"]
        }
        
        # Add network discount to output if applicable
        if copay_calc["discount"] > 0:
            decision["network_discount"] = copay_calc["discount"]
        
        # Set final decision
        if decision["decision"] != "PARTIAL":
            decision["decision"] = "APPROVED"
            decision["confidence_score"] = 0.95
        else:
            decision["confidence_score"] = 0.92
        
        decision["notes"] = f"Claim processed successfully. Category: {category}"
        
        return decision
    
    def _validate_documents(self, claim_data):
        """
        Validate all required documents are present and valid
        
        Returns:
            dict: {valid: bool, reasons: list}
        """
        reasons = []
        
        # Check completeness
        is_complete, missing = check_document_completeness(claim_data)
        if not is_complete:
            reasons.append("MISSING_DOCUMENTS")
            return {"valid": False, "reasons": reasons}
        
        prescription = claim_data.get("prescription", {})
        bill = claim_data.get("bill", {})
        
        # Validate doctor registration
        doctor_reg = prescription.get("doctor_reg")
        if not validate_doctor_registration(doctor_reg):
            reasons.append("INVALID_DOCTOR_REG")
        
        # Check for required fields in prescription
        if not prescription.get("diagnosis"):
            reasons.append("INVALID_PRESCRIPTION")
        
        # Check patient name consistency
        if prescription.get("patient_name") and bill.get("patient_name"):
            if not self._names_match(prescription["patient_name"], bill["patient_name"]):
                reasons.append("PATIENT_MISMATCH")
        
        # Check date consistency
        if prescription.get("treatment_date") and bill.get("bill_date"):
            if not self._dates_match(prescription["treatment_date"], bill["bill_date"]):
                reasons.append("DATE_MISMATCH")
        
        return {"valid": len(reasons) == 0, "reasons": reasons}
    
    def _check_fraud_indicators(self, claim_data, member_info):
        """
        Check for fraud indicators
        
        Returns:
            float: Fraud score (0-1, higher is more suspicious)
        """
        fraud_score = 0.0
        
        if not member_info:
            return fraud_score
        
        # Multiple claims same day (3 or more is very suspicious)
        same_day_claims = member_info.get("previous_claims_same_day", 0)
        if same_day_claims >= 3:
            fraud_score += 0.5
        elif same_day_claims >= 2:
            fraud_score += 0.3
        
        # High claim frequency
        if member_info.get("claims_last_month", 0) >= 5:
            fraud_score += 0.3
        
        # Unusually high amounts relative to patterns
        claim_amount = member_info.get("claim_amount", 0)
        if claim_amount > 4500:
            fraud_score += 0.1
        
        return min(fraud_score, 1.0)
    
    def _is_network_hospital(self, hospital_name):
        """Check if hospital is in network"""
        if not hospital_name:
            return False
        
        network_hospitals = [
            "Apollo", "Fortis", "Max", "Manipal", "Narayana"
        ]
        
        hospital_lower = hospital_name.lower()
        return any(net.lower() in hospital_lower for net in network_hospitals)
    
    def _calculate_excluded_amount(self, bill, excluded_items):
        """Calculate total amount of excluded items"""
        excluded_amount = 0
        
        if not bill or not excluded_items:
            return excluded_amount
        
        # Check bill items
        items = bill.get("items", [])
        for item in items:
            item_name = item.get("name", "").lower()
            for excluded in excluded_items:
                if excluded.lower() in item_name:
                    excluded_amount += item.get("amount", 0)
        
        # Check specific charges for cosmetic procedures
        for excluded in excluded_items:
            excluded_lower = excluded.lower()
            if "whitening" in excluded_lower or "cosmetic" in excluded_lower:
                excluded_amount += bill.get("teeth_whitening", 0)
            if "weight" in excluded_lower or "diet" in excluded_lower:
                excluded_amount += bill.get("diet_plan", 0)
        
        return excluded_amount
    
    def _names_match(self, name1, name2):
        """Check if two names are similar enough"""
        if not name1 or not name2:
            return True
        
        # Simple similarity check
        name1 = name1.lower().strip()
        name2 = name2.lower().strip()
        
        # Exact match
        if name1 == name2:
            return True
        
        # Allow minor variations (e.g., initials)
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        # At least 50% overlap
        overlap = len(words1.intersection(words2))
        return overlap >= min(len(words1), len(words2)) * 0.5
    
    def _dates_match(self, date1, date2):
        """Check if two dates are close enough"""
        if not date1 or not date2:
            return True
        
        try:
            if isinstance(date1, str):
                date1 = datetime.strptime(date1, "%Y-%m-%d")
            if isinstance(date2, str):
                date2 = datetime.strptime(date2, "%Y-%m-%d")
            
            # Allow 1 day difference
            diff = abs((date1 - date2).days)
            return diff <= 1
        except:
            return True