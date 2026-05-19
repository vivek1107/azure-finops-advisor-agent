import json
from typing import Dict, List
import pandas as pd
import streamlit as st

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

REQUIRED_COLUMNS = [
    "Date", "Subscription", "ResourceGroup", "ServiceName", "ResourceName",
    "MeterCategory", "Region", "Environment", "Owner", "Cost",
    "UsageQuantity", "CostCenter"
]

TAG_COLUMNS = ["Environment", "Owner", "CostCenter"]


def load_cost_data(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file)
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0)
    df["UsageQuantity"] = pd.to_numeric(df["UsageQuantity"], errors="coerce").fillna(0)

    for col in TAG_COLUMNS:
        df[col] = df[col].fillna("").astype(str).str.strip()

    return df


def summarize_costs(df: pd.DataFrame) -> Dict:
    total_cost = float(df["Cost"].sum())

    top_services = (
        df.groupby("ServiceName", dropna=False)["Cost"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
    )

    top_resource_groups = (
        df.groupby("ResourceGroup", dropna=False)["Cost"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
    )

    cost_by_environment = (
        df.groupby("Environment", dropna=False)["Cost"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )

    cost_by_subscription = (
        df.groupby("Subscription", dropna=False)["Cost"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )

    return {
        "total_cost": total_cost,
        "top_services": top_services,
        "top_resource_groups": top_resource_groups,
        "cost_by_environment": cost_by_environment,
        "cost_by_subscription": cost_by_subscription,
    }


def check_tag_governance(df: pd.DataFrame) -> pd.DataFrame:
    issues = []

    for _, row in df.iterrows():
        missing_tags = []
        for tag in TAG_COLUMNS:
            value = str(row.get(tag, "")).strip()
            if value == "" or value.lower() in ["nan", "none", "null", "tbd"]:
                missing_tags.append(tag)

        if missing_tags:
            issues.append({
                "ResourceName": row["ResourceName"],
                "ResourceGroup": row["ResourceGroup"],
                "ServiceName": row["ServiceName"],
                "Environment": row["Environment"],
                "MissingTags": ", ".join(missing_tags),
                "Cost": round(float(row["Cost"]), 2),
            })

    if not issues:
        return pd.DataFrame(columns=[
            "ResourceName", "ResourceGroup", "ServiceName",
            "Environment", "MissingTags", "Cost"
        ])

    return pd.DataFrame(issues).sort_values(by="Cost", ascending=False)


def detect_cost_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    anomalies = []

    daily_service_cost = (
        df.groupby(["Date", "ServiceName"], dropna=False)["Cost"]
        .sum()
        .reset_index()
        .sort_values(["ServiceName", "Date"])
    )

    for service_name in daily_service_cost["ServiceName"].unique():
        service_df = daily_service_cost[daily_service_cost["ServiceName"] == service_name].copy()

        if len(service_df) < 2:
            continue

        latest_row = service_df.iloc[-1]
        previous_avg = float(service_df.iloc[:-1]["Cost"].mean())

        if previous_avg <= 0:
            continue

        increase_percent = ((float(latest_row["Cost"]) - previous_avg) / previous_avg) * 100

        if increase_percent > 50 and float(latest_row["Cost"]) > 50:
            anomalies.append({
                "ServiceName": service_name,
                "LatestDate": latest_row["Date"].date(),
                "LatestCost": round(float(latest_row["Cost"]), 2),
                "PreviousAverageCost": round(previous_avg, 2),
                "IncreasePercent": round(increase_percent, 1),
            })

    if not anomalies:
        return pd.DataFrame(columns=[
            "ServiceName", "LatestDate", "LatestCost",
            "PreviousAverageCost", "IncreasePercent"
        ])

    return pd.DataFrame(anomalies).sort_values(by="IncreasePercent", ascending=False)


def identify_optimization_candidates(df: pd.DataFrame) -> pd.DataFrame:
    candidates = []

    for _, row in df.iterrows():
        service = str(row["ServiceName"]).lower()
        environment = str(row["Environment"]).lower()
        cost = float(row["Cost"])

        reason = None
        recommendation = None

        if "virtual machine" in service and environment in ["dev", "test"] and cost > 75:
            reason = "High-cost VM detected in a non-production environment."
            recommendation = "Review right-sizing, schedule-based shutdown, reserved instances, or decommissioning."

        elif "app service" in service and environment in ["dev", "test"] and cost > 50:
            reason = "App Service cost is relatively high for a non-production environment."
            recommendation = "Review SKU, scale settings, idle app plans, and environment-specific sizing."

        elif "azure openai" in service and cost > 100:
            reason = "Azure OpenAI is a significant AI workload cost driver."
            recommendation = "Review model choice, prompt length, token usage, caching, throttling, and usage limits."

        elif ("ai search" in service or "search" in service) and cost > 75:
            reason = "Search service is a notable cost driver."
            recommendation = "Review replicas, partitions, indexing frequency, semantic ranking usage, and query patterns."

        elif "storage" in service and cost > 50:
            reason = "Storage cost may benefit from lifecycle governance."
            recommendation = "Review access tiers, retention, lifecycle policies, snapshots, and unused data."

        elif "databricks" in service and cost > 100:
            reason = "Databricks cost is a significant analytics workload driver."
            recommendation = "Review cluster sizing, auto-termination, job scheduling, Photon usage, and workload ownership."

        if reason:
            candidates.append({
                "ResourceName": row["ResourceName"],
                "ResourceGroup": row["ResourceGroup"],
                "ServiceName": row["ServiceName"],
                "Environment": row["Environment"],
                "Cost": round(cost, 2),
                "Reason": reason,
                "Recommendation": recommendation,
            })

    if not candidates:
        return pd.DataFrame(columns=[
            "ResourceName", "ResourceGroup", "ServiceName", "Environment",
            "Cost", "Reason", "Recommendation"
        ])

    return pd.DataFrame(candidates).sort_values(by="Cost", ascending=False)


def build_rule_based_recommendations(summary: Dict, tag_issues: pd.DataFrame,
                                     anomalies: pd.DataFrame, candidates: pd.DataFrame) -> List[str]:
    recommendations = []
    total_cost = summary["total_cost"]
    top_services = summary["top_services"]

    if not top_services.empty and total_cost > 0:
        top_service = top_services.iloc[0]["ServiceName"]
        top_service_cost = float(top_services.iloc[0]["Cost"])
        percentage = (top_service_cost / total_cost) * 100
        recommendations.append(
            f"Prioritize review of {top_service}, which represents approximately {percentage:.1f}% of the analyzed spend."
        )

    if not tag_issues.empty:
        recommendations.append(
            f"Improve tag governance. {len(tag_issues)} resource cost records are missing one or more required tags: Environment, Owner, or CostCenter."
        )

    if not anomalies.empty:
        recommendations.append(
            f"Investigate {len(anomalies)} potential cost anomaly/anomalies where latest daily spend increased significantly compared with the previous average."
        )

    if not candidates.empty:
        recommendations.append(
            f"Review {len(candidates)} optimization candidate(s), focusing first on high-cost non-production resources and AI/search cost drivers."
        )

    recommendations.append(
        "Introduce ownership-based cost reporting using Owner, Environment, and CostCenter to support showback or chargeback conversations."
    )
    recommendations.append(
        "For AI workloads, track token usage, model selection, prompt length, user volume, retrieval frequency, and supporting Azure service costs."
    )
    recommendations.append(
        "Create a monthly FinOps review cadence covering top services, anomalies, non-production spend, tag compliance, and optimization actions."
    )

    return recommendations


def create_rule_based_executive_summary(summary: Dict, tag_issues: pd.DataFrame,
                                        anomalies: pd.DataFrame, candidates: pd.DataFrame) -> str:
    total_cost = summary["total_cost"]
    top_service_text = "No service cost data available."

    if not summary["top_services"].empty and total_cost > 0:
        top_service = summary["top_services"].iloc[0]["ServiceName"]
        top_service_cost = float(summary["top_services"].iloc[0]["Cost"])
        percentage = (top_service_cost / total_cost) * 100
        top_service_text = (
            f"The largest cost driver is {top_service}, representing approximately {percentage:.1f}% "
            "of the analyzed spend."
        )

    return (
        "The analyzed Azure cost dataset shows opportunities to improve cost visibility, "
        "tag governance, and optimization discipline. "
        f"{top_service_text} "
        f"There are {len(tag_issues)} missing tag issue(s), {len(anomalies)} potential cost anomaly/anomalies, "
        f"and {len(candidates)} optimization candidate(s). "
        "Recommended focus areas include ownership-based reporting, review of top cost-driving services, "
        "non-production workload optimization, and dedicated FinOps review cycles for AI-related cost drivers."
    )


def generate_executive_summary_with_ollama(summary: Dict, tag_issues: pd.DataFrame,
                                           anomalies: pd.DataFrame, candidates: pd.DataFrame,
                                           recommendations: List[str], model: str) -> str:
    if not OLLAMA_AVAILABLE:
        return "Ollama is not available in this environment. Using the rule-based FinOps summary instead."

    prompt = f"""
You are an Azure FinOps Advisor Agent.

Create an executive-ready Azure FinOps summary based on the following analysis.

Total Cost: {summary["total_cost"]:.2f}

Top Services:
{summary["top_services"].to_string(index=False)}

Cost by Environment:
{summary["cost_by_environment"].to_string(index=False)}

Tag Issues Count: {len(tag_issues)}
Cost Anomalies Count: {len(anomalies)}
Optimization Candidates Count: {len(candidates)}

Rule-Based Recommendations:
{json.dumps(recommendations, indent=2)}

Write these sections:
1. Executive Summary
2. Key Cost Drivers
3. Governance Gaps
4. Recommended Actions
5. Suggested Next Steps

Keep it concise, professional, and suitable for cloud leadership, platform teams, and FinOps stakeholders.
"""

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": "You are a senior Azure FinOps and Cloud Architecture advisor."},
            {"role": "user", "content": prompt},
        ],
        options={"temperature": 0.2},
    )
    return response["message"]["content"]


def create_markdown_report(summary: Dict, tag_issues: pd.DataFrame,
                           anomalies: pd.DataFrame, candidates: pd.DataFrame,
                           recommendations: List[str], executive_summary: str) -> str:
    lines = []
    lines.append("# Azure FinOps Advisor Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(executive_summary)
    lines.append("")
    lines.append("## Total Analyzed Cost")
    lines.append(f"- Total cost: {summary['total_cost']:.2f}")
    lines.append("")
    lines.append("## Top Services")
    if summary["top_services"].empty:
        lines.append("- No service cost data available.")
    else:
        for _, row in summary["top_services"].iterrows():
            lines.append(f"- {row['ServiceName']}: {row['Cost']:.2f}")
    lines.append("")
    lines.append("## Cost by Environment")
    if summary["cost_by_environment"].empty:
        lines.append("- No environment cost data available.")
    else:
        for _, row in summary["cost_by_environment"].iterrows():
            env = row["Environment"] if str(row["Environment"]).strip() else "Unassigned"
            lines.append(f"- {env}: {row['Cost']:.2f}")
    lines.append("")
    lines.append("## Governance Findings")
    if tag_issues.empty:
        lines.append("- No missing tag issues found.")
    else:
        lines.append(f"- {len(tag_issues)} resource cost record(s) have missing tag information.")
    lines.append("")
    lines.append("## Cost Anomaly Findings")
    if anomalies.empty:
        lines.append("- No major cost anomalies detected using the current rule-based check.")
    else:
        for _, row in anomalies.iterrows():
            lines.append(f"- {row['ServiceName']} increased by {row['IncreasePercent']}% on {row['LatestDate']}.")
    lines.append("")
    lines.append("## Optimization Candidates")
    if candidates.empty:
        lines.append("- No optimization candidates detected by the current rules.")
    else:
        for _, row in candidates.head(10).iterrows():
            lines.append(f"- {row['ResourceName']} ({row['ServiceName']}): {row['Recommendation']}")
    lines.append("")
    lines.append("## Recommended Actions")
    for recommendation in recommendations:
        lines.append(f"- {recommendation}")

    return "\n".join(lines)


def main() -> None:
    st.set_page_config(page_title="Azure FinOps Advisor Agent", page_icon="💰", layout="wide")
    st.title("💰 Azure FinOps Advisor Agent")
    st.caption(
        "A lightweight AI-assisted tool for Azure cost analysis, governance checks, anomaly detection, and FinOps recommendations."
    )

    with st.sidebar:
        st.header("Settings")
        use_ollama = st.checkbox(
            "Use local Ollama for executive summary",
            value=False,
            help="Optional. The app works without Ollama by using rule-based recommendations.",
        )
        ollama_model = st.text_input("Ollama model", value="llama3.2:3b")
        st.info("Upload the sample CSV from sample_data or your own Azure-style cost export.")

    uploaded_file = st.file_uploader("Upload Azure cost export CSV", type=["csv"])

    if uploaded_file is None:
        st.info("Upload a CSV file with Azure cost data to begin.")
        st.markdown(
            "Required columns: `Date, Subscription, ResourceGroup, ServiceName, ResourceName, "
            "MeterCategory, Region, Environment, Owner, Cost, UsageQuantity, CostCenter`"
        )
        return

    try:
        df = load_cost_data(uploaded_file)
    except Exception as exc:
        st.error(f"Could not load file: {exc}")
        return

    st.success("Cost data loaded successfully.")

    summary = summarize_costs(df)
    tag_issues = check_tag_governance(df)
    anomalies = detect_cost_anomalies(df)
    candidates = identify_optimization_candidates(df)
    recommendations = build_rule_based_recommendations(summary, tag_issues, anomalies, candidates)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cost", f"{summary['total_cost']:.2f}")
    col2.metric("Resources", df["ResourceName"].nunique())
    col3.metric("Missing Tag Issues", len(tag_issues))
    col4.metric("Optimization Candidates", len(candidates))

    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Cost Summary", "Governance", "Anomalies", "Optimization", "Executive Report"]
    )

    with tab1:
        st.subheader("Top Services by Cost")
        st.dataframe(summary["top_services"], use_container_width=True)
        if not summary["top_services"].empty:
            st.bar_chart(summary["top_services"], x="ServiceName", y="Cost")

        st.subheader("Cost by Environment")
        st.dataframe(summary["cost_by_environment"], use_container_width=True)

        st.subheader("Cost by Resource Group")
        st.dataframe(summary["top_resource_groups"], use_container_width=True)

    with tab2:
        st.subheader("Tag Governance Issues")
        if tag_issues.empty:
            st.success("No missing tag issues found.")
        else:
            st.warning("Some resources are missing required tags.")
            st.dataframe(tag_issues, use_container_width=True)

    with tab3:
        st.subheader("Potential Cost Anomalies")
        if anomalies.empty:
            st.success("No major anomalies detected using the current rule.")
        else:
            st.warning("Potential anomalies detected.")
            st.dataframe(anomalies, use_container_width=True)

    with tab4:
        st.subheader("Optimization Candidates")
        if candidates.empty:
            st.success("No optimization candidates detected using the current rules.")
        else:
            st.dataframe(candidates, use_container_width=True)

        st.subheader("Rule-Based Recommendations")
        for recommendation in recommendations:
            st.markdown(f"- {recommendation}")

    with tab5:
        st.subheader("Executive FinOps Report")

        if use_ollama:
            with st.spinner("Generating executive summary using local Ollama model..."):
                try:
                    executive_summary = generate_executive_summary_with_ollama(
                        summary, tag_issues, anomalies, candidates, recommendations, ollama_model
                    )
                except Exception as exc:
                    st.warning(f"Ollama summary generation failed: {exc}")
                    executive_summary = create_rule_based_executive_summary(
                        summary, tag_issues, anomalies, candidates
                    )
        else:
            executive_summary = create_rule_based_executive_summary(
                summary, tag_issues, anomalies, candidates
            )

        st.markdown(executive_summary)

        report = create_markdown_report(
            summary, tag_issues, anomalies, candidates, recommendations, executive_summary
        )

        st.download_button(
            label="Download FinOps Report",
            data=report,
            file_name="azure_finops_advisor_report.md",
            mime="text/markdown",
        )


if __name__ == "__main__":
    main()
