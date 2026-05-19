# Azure FinOps Advisor Agent

A lightweight AI-assisted Azure FinOps tool that analyzes Azure-style cost data and generates cost, governance, anomaly, and optimization insights.

## What It Does

This project helps analyze Azure cost export-style data and generates:

- Total cloud spend summary
- Top cost-driving services
- Cost by subscription, resource group, and environment
- Missing tag governance findings
- Simple cost anomaly detection
- Optimization candidate identification
- Rule-based FinOps recommendations
- Optional local LLM-generated executive summary using Ollama
- Downloadable Markdown FinOps report

## Why I Built This

Cloud cost management is not only a finance topic. It is also an architecture, governance, and operational discipline.

This project explores how AI-assisted workflows can support Azure FinOps conversations by converting cost data into structured insights and practical recommendations.

It is designed as a lightweight portfolio project for:

- Azure architects
- Cloud governance teams
- FinOps practitioners
- Platform engineering teams
- Cloud advisory and customer success scenarios

## Tech Stack

- Python
- Streamlit
- Pandas
- Ollama optional
- Local open-source LLM optional

## Folder Structure

```text
azure-finops-advisor-agent/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
└── sample_data/
    └── sample_azure_cost_data.csv
```

## How to Run

1. Install Python 3.10 or above.
2. Install project dependencies from `requirements.txt`.
3. Run the Streamlit app from the project folder.
4. Upload the sample CSV file from the `sample_data` folder.
5. Review cost summary, governance gaps, anomalies, optimization candidates, and the executive report.

## Optional Local AI Summary

The app works without Ollama because it includes rule-based recommendations.

If Ollama is installed and a local model such as Llama 3.2 is available, enable the sidebar option:

`Use local Ollama for executive summary`

This will generate a more narrative executive FinOps summary using the local model.

## Required CSV Columns

The uploaded CSV should include:

- Date
- Subscription
- ResourceGroup
- ServiceName
- ResourceName
- MeterCategory
- Region
- Environment
- Owner
- Cost
- UsageQuantity
- CostCenter

A sample file is included in:

`sample_data/sample_azure_cost_data.csv`

## Sample Use Cases

- Azure cost review
- FinOps advisory discussion
- Cloud governance review
- Tagging compliance analysis
- AI workload cost review
- Non-production spend optimization
- Executive cost reporting

## Future Enhancements

- Azure Cost Management export integration
- Azure Retail Prices API integration
- Budget and forecast analysis
- AI workload token-cost estimator
- Chargeback and showback reporting
- LangGraph-based multi-agent FinOps workflow
- Azure OpenAI version for enterprise deployment

## Note

This is a portfolio and learning project using sample data only. It does not include confidential customer data or live Azure subscription access.
