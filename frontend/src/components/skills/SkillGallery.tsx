/**
 * SkillGallery.tsx - Browse, enable, and configure skills
 */

import React, { useState, useEffect } from 'react';

interface Skill {
  name: string;
  description: string;
  trigger: string;
  aliases: string[];
  enabled: boolean;
  priority: number;
  requires_online: boolean;
  cooldown_seconds: number;
  source: 'built_in' | 'toml';
  executions?: number;
  success_rate?: number;
}

interface SkillGalleryProps {
  onSkillToggle?: (name: string, enabled: boolean) => void;
  onSkillEdit?: (name: string) => void;
}

export const SkillGallery: React.FC<SkillGalleryProps> = ({
  onSkillToggle,
  onSkillEdit,
}) => {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'enabled' | 'disabled'>('all');
  const [search, setSearch] = useState('');
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);

  useEffect(() => {
    loadSkills();
  }, []);

  const loadSkills = async () => {
    try {
      const res = await fetch('http://localhost:8766/skills');
      if (res.ok) {
        const data = await res.json();
        const allSkills = [
          ...(data.built_in || []).map((s: any) => ({ ...s, source: 'built_in' as const })),
          ...(data.loaded || []).map((s: any) => ({ ...s, source: 'toml' as const })),
        ];
        setSkills(allSkills);
      }
    } catch (err) {
      console.error('Failed to load skills:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleSkill = async (skill: Skill) => {
    try {
      const res = await fetch(`http://localhost:8766/skills/${skill.name}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !skill.enabled }),
      });

      if (res.ok) {
        setSkills(skills.map(s =>
          s.name === skill.name ? { ...s, enabled: !s.enabled } : s
        ));
        onSkillToggle?.(skill.name, !skill.enabled);
      }
    } catch (err) {
      console.error('Failed to toggle skill:', err);
    }
  };

  const filteredSkills = skills.filter(skill => {
    if (filter === 'enabled' && !skill.enabled) return false;
    if (filter === 'disabled' && skill.enabled) return false;
    if (search && !skill.name.toLowerCase().includes(search.toLowerCase()) &&
        !skill.description.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  if (loading) {
    return (
      <div className="skill-gallery loading">
        <p>Loading skills...</p>
      </div>
    );
  }

  return (
    <div className="skill-gallery">
      <div className="skill-gallery-header">
        <h2>Skill Gallery</h2>
        <div className="skill-gallery-controls">
          <input
            type="text"
            autoComplete="off"
            placeholder="Search skills..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="skill-search"
          />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as any)}
            className="skill-filter"
          >
            <option value="all">All Skills</option>
            <option value="enabled">Enabled</option>
            <option value="disabled">Disabled</option>
          </select>
        </div>
      </div>

      <div className="skill-stats">
        <div className="stat-card">
          <span className="stat-value">{skills.length}</span>
          <span className="stat-label">Total Skills</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{skills.filter(s => s.enabled).length}</span>
          <span className="stat-label">Enabled</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{skills.filter(s => s.source === 'toml').length}</span>
          <span className="stat-label">Custom</span>
        </div>
      </div>

      <div className="skill-list">
        {filteredSkills.map(skill => (
          <div
            key={skill.name}
            className={`skill-card ${skill.enabled ? 'enabled' : 'disabled'} ${skill.source}`}
            onClick={() => setSelectedSkill(skill)}
          >
            <div className="skill-card-header">
              <h3>{skill.name}</h3>
              <span className={`skill-badge ${skill.source}`}>
                {skill.source === 'built_in' ? 'Built-in' : 'Custom'}
              </span>
            </div>

            <p className="skill-description">{skill.description}</p>

            <div className="skill-meta">
              <span className="skill-trigger">
                Trigger: <code>{skill.trigger || 'N/A'}</code>
              </span>
              {skill.requires_online && (
                <span className="skill-requires-online">🌐 Online</span>
              )}
              {skill.cooldown_seconds > 0 && (
                <span className="skill-cooldown">
                  ⏱️ {skill.cooldown_seconds}s cooldown
                </span>
              )}
            </div>

            {skill.executions !== undefined && (
              <div className="skill-stats-mini">
                <span>{skill.executions} executions</span>
                {skill.success_rate !== undefined && (
                  <span>{skill.success_rate.toFixed(1)}% success</span>
                )}
              </div>
            )}

            <div className="skill-card-actions">
              <button
                className={`toggle-btn ${skill.enabled ? 'active' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  toggleSkill(skill);
                }}
              >
                {skill.enabled ? '✓ Enabled' : '✕ Disabled'}
              </button>
              {skill.source === 'toml' && (
                <button
                  className="edit-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSkillEdit?.(skill.name);
                  }}
                >
                  Edit
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {selectedSkill && (
        <div className="skill-modal" onClick={() => setSelectedSkill(null)}>
          <div className="skill-modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setSelectedSkill(null)}>×</button>
            <h2>{selectedSkill.name}</h2>
            <p>{selectedSkill.description}</p>

            <div className="skill-details">
              <div className="detail-row">
                <strong>Trigger:</strong> {selectedSkill.trigger || 'N/A'}
              </div>
              {selectedSkill.aliases?.length > 0 && (
                <div className="detail-row">
                  <strong>Aliases:</strong> {selectedSkill.aliases.join(', ')}
                </div>
              )}
              <div className="detail-row">
                <strong>Priority:</strong> {selectedSkill.priority}
              </div>
              <div className="detail-row">
                <strong>Requires Online:</strong> {selectedSkill.requires_online ? 'Yes' : 'No'}
              </div>
              <div className="detail-row">
                <strong>Cooldown:</strong> {selectedSkill.cooldown_seconds}s
              </div>
              <div className="detail-row">
                <strong>Source:</strong> {selectedSkill.source}
              </div>
            </div>

            <div className="skill-modal-actions">
              <button
                className={`toggle-btn large ${selectedSkill.enabled ? 'active' : ''}`}
                onClick={() => toggleSkill(selectedSkill)}
              >
                {selectedSkill.enabled ? 'Disable Skill' : 'Enable Skill'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillGallery;
