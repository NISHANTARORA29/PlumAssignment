"""
Policy Validation Module - FIXED VERSION v2
Validates claims against policy terms and coverage rules
"""
import json
from datetime import datetime, timedelta
from pathlib import Path


class PolicyValidator:
    def __init__(self, policy_path="policy_terms.json"):
        """Initialize with policy terms"""
        with open(policy_path, 'r') as f:
            self.policy = json.load(f)
    
    def check_member_eligibility(self, member_id, treatment_date):
        """
        Check if member is eligible for claim
        
        Args:
            member_id: Member ID
            treatment_date: Date of treatment (string or datetime)
            
        Returns:
            dict: {eligible: bool, reason: str}
        """
        # For simplicity, assuming all members are valid
        # In real scenario, check against member database
        if not member_id:
            return {"eligible": False, "reason": "MEMBER_NOT_FOUND"}
        
        # Check policy status
        policy_start = datetime.strptime(self.policy["effective_date"], "%Y-%m-%d")
        if isinstance(treatment_date, str):
            treatment_date = datetime.strptime(treatment_date, "%Y-%m-%d")
        
        if treatment_date < policy_start:
            return {"eligible": False, "reason": "POLICY_INACTIVE"}
        
        return {"eligible": True, "reason": None}
    
    def check_waiting_period(self, member_join_date, treatment_date, diagnosis):
        """
        Check if waiting period is satisfied for the condition
        
        Args:
            member_join_date: When member joined policy
            treatment_date: Date of treatment
            diagnosis: Medical diagnosis
            
        Returns:
            dict: {satisfied: bool, reason: str, eligible_date: str}
        """
        if isinstance(member_join_date, str):
            member_join_date = datetime.strptime(member_join_date, "%Y-%m-%d")
        if isinstance(treatment_date, str):
            treatment_date = datetime.strptime(treatment_date, "%Y-%m-%d")
        
        waiting_periods = self.policy["waiting_periods"]
        diagnosis_lower = diagnosis.lower() if diagnosis else ""
        
        # Check for specific ailments
        for ailment, days in waiting_periods["specific_ailments"].items():
            if ailment.lower() in diagnosis_lower:
                eligible_date = member_join_date + timedelta(days=days)
                if treatment_date < eligible_date:
                    return {
                        "satisfied": False,
                        "reason": "WAITING_PERIOD",
                        "eligible_date": eligible_date.strftime("%Y-%m-%d"),
                        "condition": ailment
                    }
        
        # Check initial waiting period
        initial_eligible = member_join_date + timedelta(days=waiting_periods["initial_waiting"])
        if treatment_date < initial_eligible:
            return {
                "satisfied": False,
                "reason": "WAITING_PERIOD",
                "eligible_date": initial_eligible.strftime("%Y-%m-%d"),
                "condition": "initial"
            }
        
        return {"satisfied": True, "reason": None}
    
    def check_coverage(self, diagnosis, treatments, medicines):
        """
        Check if diagnosis and treatments are covered
        
        Args:
            diagnosis: Medical diagnosis
            treatments: List of treatments/procedures
            medicines: List of medicines
            
        Returns:
            dict: {covered: bool, excluded_items: list, category: str, partial_coverage: bool}
        """
        diagnosis_lower = diagnosis.lower() if diagnosis else ""
        excluded_items = []
        
        # Define exclusion keywords with PRIMARY vs SECONDARY classification
        primary_exclusions = {
            # These make the ENTIRE claim non-covered
            "weight loss": ["obesity", "weight loss", "bariatric"],
            "infertility": ["infertility", "ivf", "fertility treatment"],
            "experimental": ["experimental", "investigational"],
        }
        
        secondary_exclusions = {
            # These can be excluded while rest of claim is covered
            "cosmetic": ["cosmetic", "aesthetic", "beautification", "whitening"],
            "supplements": ["diet plan", "weight management program"],
        }
        
        # Check if PRIMARY diagnosis/treatment is excluded
        primary_excluded = False
        for exclusion_type, keywords in primary_exclusions.items():
            for keyword in keywords:
                if keyword in diagnosis_lower:
                    excluded_items.append(exclusion_type)
                    primary_excluded = True
                    break
        
        # If primary diagnosis is excluded, entire claim is not covered
        if primary_excluded:
            return {
                "covered": False,
                "excluded_items": excluded_items,
                "category": "exclusion",
                "partial_coverage": False
            }
        
        # Check treatments for both primary and secondary exclusions
        partial_exclusions = []
        if treatments:
            for treatment in treatments:
                treatment_lower = treatment.lower()
                
                # Check primary exclusions in treatments
                for exclusion_type, keywords in primary_exclusions.items():
                    for keyword in keywords:
                        if keyword in treatment_lower:
                            # If treatment contains primary exclusion, check if it's the MAIN treatment
                            # For TC009, "Bariatric consultation and diet plan" is PRIMARY
                            excluded_items.append(treatment)
                            primary_excluded = True
                            break
                
                # Check secondary exclusions (cosmetic procedures)
                for exclusion_type, keywords in secondary_exclusions.items():
                    for keyword in keywords:
                        if keyword in treatment_lower:
                            partial_exclusions.append(treatment)
                            break
        
        # If primary treatment is excluded, entire claim is not covered
        if primary_excluded:
            return {
                "covered": False,
                "excluded_items": excluded_items,
                "category": "exclusion",
                "partial_coverage": False
            }
        
        # If only secondary items are excluded, claim is partially covered
        if partial_exclusions:
            excluded_items.extend(partial_exclusions)
            category = self.determine_claim_category(diagnosis, treatments)
            return {
                "covered": True,
                "excluded_items": excluded_items,
                "category": category,
                "partial_coverage": True
            }
        
        # Determine category
        category = self.determine_claim_category(diagnosis, treatments)
        
        return {
            "covered": True,
            "excluded_items": [],
            "category": category,
            "partial_coverage": False
        }
    
    def determine_claim_category(self, diagnosis, treatments):
        """
        Determine which policy category the claim falls under
        
        Returns:
            str: Category name (consultation_fees, dental, pharmacy, etc.)
        """
        diagnosis_lower = diagnosis.lower() if diagnosis else ""
        treatments_str = " ".join(treatments).lower() if treatments else ""
        combined = diagnosis_lower + " " + treatments_str
        
        # Dental
        dental_keywords = ["tooth", "dental", "root canal", "filling", "extraction", "decay"]
        if any(kw in combined for kw in dental_keywords):
            return "dental"
        
        # Vision
        vision_keywords = ["eye", "vision", "glasses", "contact lens", "lasik"]
        if any(kw in combined for kw in vision_keywords):
            return "vision"
        
        # Alternative medicine
        alt_keywords = ["ayurved", "homeopath", "unani", "panchakarma", "chronic joint"]
        if any(kw in combined for kw in alt_keywords):
            return "alternative_medicine"
        
        # Diagnostic tests (when primary complaint is test)
        diagnostic_keywords = ["mri", "ct scan", "ultrasound", "x-ray"]
        if any(kw in combined for kw in diagnostic_keywords):
            return "diagnostic_tests"
        
        # Default to consultation
        return "consultation_fees"
    
    def check_limits(self, claim_amount, category, member_previous_claims=0):
        """
        Check if claim amount is within policy limits
        
        Args:
            claim_amount: Total claim amount (AFTER exclusions removed)
            category: Claim category
            member_previous_claims: Total previous claims this year
            
        Returns:
            dict: {within_limits: bool, limit_type: str, max_allowed: float}
        """
        coverage = self.policy["coverage_details"]
        
        # Check minimum claim amount
        min_claim = self.policy["claim_requirements"]["minimum_claim_amount"]
        if claim_amount < min_claim:
            return {
                "within_limits": False,
                "limit_type": "BELOW_MIN_AMOUNT",
                "max_allowed": min_claim
            }
        
        # KEY FIX: Check category sub-limit FIRST for specialized categories
        # Dental, vision, alternative medicine have their own higher sub-limits
        # These should be checked BEFORE the general per-claim limit
        category_limits = {
            "diagnostic_tests": coverage["diagnostic_tests"]["sub_limit"],
            "pharmacy": coverage["pharmacy"]["sub_limit"],
            "dental": coverage["dental"]["sub_limit"],
            "vision": coverage["vision"]["sub_limit"],
            "alternative_medicine": coverage["alternative_medicine"]["sub_limit"]
        }
        
        if category in category_limits:
            sub_limit = category_limits[category]
            if claim_amount > sub_limit:
                return {
                    "within_limits": False,
                    "limit_type": "SUB_LIMIT_EXCEEDED",
                    "max_allowed": sub_limit
                }
        else:
            # For consultation_fees and other categories, check per-claim limit
            per_claim_limit = coverage["per_claim_limit"]
            if claim_amount > per_claim_limit:
                return {
                    "within_limits": False,
                    "limit_type": "PER_CLAIM_EXCEEDED",
                    "max_allowed": per_claim_limit
                }
        
        # Check annual limit
        total_claims = member_previous_claims + claim_amount
        if total_claims > coverage["annual_limit"]:
            return {
                "within_limits": False,
                "limit_type": "ANNUAL_LIMIT_EXCEEDED",
                "max_allowed": coverage["annual_limit"] - member_previous_claims
            }
        
        return {"within_limits": True, "limit_type": None}
    
    def calculate_copay(self, claim_amount, category, is_network=False):
        coverage = self.policy["coverage_details"]

        copay_amount = 0
        discount_amount = 0

        if category == "consultation_fees":
            cfg = coverage["consultation_fees"]

            copay_pct = cfg.get("copay_percentage", 0) / 100.0
            network_pct = cfg.get("network_discount", 0) / 100.0

            # Always apply copay (network or non-network)
            copay_amount = claim_amount * copay_pct

            # If network → apply extra discount
            if is_network:
                # network discount = total network benefit minus copay
                extra_discount_rate = max(network_pct - copay_pct, 0)
                discount_amount = claim_amount * extra_discount_rate

        else:
            # fallback (if needed later)
            pass

        net_payable = claim_amount - copay_amount - discount_amount

        return {
            "copay_amount": round(copay_amount, 2),
            "discount": round(discount_amount, 2),
            "net_payable": round(net_payable, 2)
        }


    
    def requires_preauth(self, treatments, tests):
        """
        Check if pre-authorization is required
        
        Args:
            treatments: List of treatments
            tests: List of diagnostic tests
            
        Returns:
            bool: True if pre-auth required
        """
        preauth_tests = ["mri", "ct scan"]
        
        if tests:
            for test in tests:
                test_lower = test.lower()
                if any(pat in test_lower for pat in preauth_tests):
                    return True
        
        if treatments:
            for treatment in treatments:
                treatment_lower = treatment.lower()
                if any(pat in treatment_lower for pat in preauth_tests):
                    return True
        
        return False