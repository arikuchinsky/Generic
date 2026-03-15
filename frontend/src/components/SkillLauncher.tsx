import { Skill } from "../types";

interface SkillLauncherProps {
  skills: Skill[];
  onSelectSkill: (skillId: string) => void;
  onClose: () => void;
}

export function SkillLauncher({ skills, onSelectSkill, onClose }: SkillLauncherProps) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal skill-launcher-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Start a Skill</h3>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          {skills.length === 0 && (
            <div style={{ padding: "24px", textAlign: "center", color: "var(--text-tertiary)" }}>
              No skills available
            </div>
          )}
          <div className="skill-grid">
            {skills.map((skill) => (
              <div
                key={skill.id}
                className="skill-card"
                onClick={() => onSelectSkill(skill.id)}
              >
                <span className="skill-card-icon">{skill.icon}</span>
                <div className="skill-card-info">
                  <div className="skill-card-name">{skill.name}</div>
                  <div className="skill-card-desc">{skill.description}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
