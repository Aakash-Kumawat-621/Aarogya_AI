import re

with open('frontend/src/routes/_authenticated.results.$id.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add useEffect and useState to import
content = content.replace(
    'import { createFileRoute, Link } from "@tanstack/react-router";',
    'import { createFileRoute, Link } from "@tanstack/react-router";\nimport { useEffect, useState } from "react";'
)

# Add state hook inside ResultsPage
state_hook = """
  const [resultData, setResultData] = useState<{ diagnosis: any, urgency: any } | null>(null);
  
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("latest_diagnosis");
      if (stored) {
        setResultData(JSON.parse(stored));
      }
    } catch (e) {}
  }, []);
  
  const conditionName = resultData?.diagnosis?.condition_name || "Viral Fever";
  const confidence = resultData?.diagnosis?.confidence || 85;
  const urgencyLevel = resultData?.urgency?.level || "moderate";
  const explanation = resultData?.diagnosis?.explanation || "Your symptoms are most consistent with a viral infection that may be causing fever and fatigue. Most cases improve with rest, hydration, and careful monitoring, but a clinician can help confirm the cause and guide treatment.";
"""

content = content.replace(
    '  if (!id) return <PageLoadingSkeleton />;\n\n  return (',
    f'  if (!id) return <PageLoadingSkeleton />;\n{state_hook}\n  return ('
)

# Replace hardcoded values with variables
content = content.replace('>Viral Fever<', '>{conditionName}<')
content = content.replace('>85%<', '>{confidence}%<')
content = content.replace('style={{ width: "85%" }}', 'style={{ width: `${confidence}%` }}')
content = content.replace('Moderate urgency', '{urgencyLevel.charAt(0).toUpperCase() + urgencyLevel.slice(1)} urgency')

# Replace explanation text
explanation_regex = r'<p className="text-sm leading-relaxed text-muted-text">Your symptoms are most consistent with a viral infection.*?</p>'
content = re.sub(explanation_regex, '<p className="text-sm leading-relaxed text-muted-text">{explanation}</p>', content, flags=re.DOTALL)

with open('frontend/src/routes/_authenticated.results.$id.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Results page updated")
