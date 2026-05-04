/**
 * SkillDashboard.tsx - Analytics and statistics for skill usage
 */

import React, { useState, useEffect } from 'react';

interface SkillStat {
  skill_name: string;
  total_executions: number;
  successful_executions: number;
  failed_executions: number;
  total_duration_ms: number;
  success_rate?: number;
  avg_duration_ms?: number;
}

interface UsageTrend {
  date: string;
  executions: number;
  successes: number;
  avg_duration: number;
}

interface DashboardData {
  summary: {
    top_skills: SkillStat[];
    recent_executions: any[];
    failures: any[];
  };
  trends: {
    daily: UsageTrend[];
    hourly: Record<number, number>;
    day_of_week: Record<number, number>;
  };
  stats: SkillStat[] | Record<string, SkillStat>;
  generated_at: string;
}

export const SkillDashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d'>('7d');

  useEffect(() => {
    loadDashboard();
    const interval = setInterval(loadDashboard, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [timeRange]);

  const loadDashboard = async () => {
    try {
      const res = await fetch(`http://localhost:8766/skills/dashboard?range=${timeRange}`);
      if (res.ok) {
        const dashboardData = await res.json();
        setData(dashboardData);
      }
    } catch (err) {
      console.error('Failed to load dashboard:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="skill-dashboard loading">
        <p>Loading dashboard...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="skill-dashboard error">
        <p>Failed to load dashboard data</p>
        <button onClick={loadDashboard}>Retry</button>
      </div>
    );
  }

  const stats = Array.isArray(data.stats) ? data.stats : Object.values(data.stats);
  const totalExecutions = stats.reduce((sum, s) => sum + (s.total_executions || 0), 0);
  const totalSuccess = stats.reduce((sum, s) => sum + (s.successful_executions || 0), 0);
  const overallSuccessRate = totalExecutions > 0 ? (totalSuccess / totalExecutions) * 100 : 0;

  return (
    <div className="skill-dashboard">
      <div className="dashboard-header">
        <h2>Skill Analytics Dashboard</h2>
        <div className="time-range-selector">
          <button
            className={timeRange === '7d' ? 'active' : ''}
            onClick={() => setTimeRange('7d')}
          >
            7 Days
          </button>
          <button
            className={timeRange === '30d' ? 'active' : ''}
            onClick={() => setTimeRange('30d')}
          >
            30 Days
          </button>
          <button
            className={timeRange === '90d' ? 'active' : ''}
            onClick={() => setTimeRange('90d')}
          >
            90 Days
          </button>
        </div>
      </div>

      <div className="dashboard-overview">
        <div className="overview-card">
          <div className="overview-value">{totalExecutions}</div>
          <div className="overview-label">Total Executions</div>
        </div>
        <div className="overview-card">
          <div className="overview-value">{overallSuccessRate.toFixed(1)}%</div>
          <div className="overview-label">Success Rate</div>
        </div>
        <div className="overview-card">
          <div className="overview-value">{stats.length}</div>
          <div className="overview-label">Active Skills</div>
        </div>
        <div className="overview-card">
          <div className="overview-value">
            {((stats.reduce((sum, s) => sum + (s.total_duration_ms || 0), 0) / totalExecutions) || 0).toFixed(0)}ms
          </div>
          <div className="overview-label">Avg Duration</div>
        </div>
      </div>

      <div className="dashboard-grid">
        {/* Top Skills */}
        <div className="dashboard-section">
          <h3>Top Skills (by executions)</h3>
          <div className="skills-table">
            <table>
              <thead>
                <tr>
                  <th>Skill</th>
                  <th>Executions</th>
                  <th>Success Rate</th>
                  <th>Avg Duration</th>
                </tr>
              </thead>
              <tbody>
                {(data.summary.top_skills || []).map((skill, idx) => (
                  <tr key={idx}>
                    <td className="skill-name">{skill.skill_name}</td>
                    <td>{skill.total_executions}</td>
                    <td>
                      <div className="progress-bar">
                        <div
                          className="progress-fill"
                          style={{ width: `${skill.success_rate || 0}%` }}
                        />
                        <span>{skill.success_rate?.toFixed(1) || 0}%</span>
                      </div>
                    </td>
                    <td>{(skill.avg_duration_ms || 0).toFixed(0)}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Usage Trends */}
        <div className="dashboard-section">
          <h3>Daily Usage Trend</h3>
          <div className="usage-chart">
            {data.trends.daily.slice(0, 7).map((day, idx) => (
              <div key={idx} className="chart-bar">
                <div
                  className="bar"
                  style={{ height: `${Math.min(100, (day.executions / Math.max(...data.trends.daily.map(d => d.executions))) * 100)}%` }}
                />
                <div className="bar-label">{day.date.slice(5)}</div>
                <div className="bar-value">{day.executions}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Hourly Heatmap */}
        <div className="dashboard-section">
          <h3>Hourly Activity</h3>
          <div className="hourly-heatmap">
            {Array.from({ length: 24 }).map((_, hour) => {
              const count = data.trends.hourly[hour] || 0;
              const maxCount = Math.max(...Object.values(data.trends.hourly), 1);
              const intensity = count / maxCount;

              return (
                <div
                  key={hour}
                  className="heatmap-cell"
                  style={{
                    backgroundColor: `rgba(59, 130, 246, ${intensity})`,
                  }}
                  title={`${hour}:00 - ${count} executions`}
                >
                  {hour}
                </div>
              );
            })}
          </div>
        </div>

        {/* Recent Executions */}
        <div className="dashboard-section">
          <h3>Recent Executions</h3>
          <div className="recent-list">
            {(data.summary.recent_executions || []).slice(0, 10).map((exec, idx) => (
              <div key={idx} className="recent-item">
                <span className={`status-indicator ${exec.success ? 'success' : 'failure'}`} />
                <span className="skill-name">{exec.skill_name}</span>
                <span className="command-text">{exec.command_text?.slice(0, 40)}...</span>
                <span className="timestamp">{new Date(exec.created_at * 1000).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Failures */}
        {data.summary.failures?.length > 0 && (
          <div className="dashboard-section">
            <h3>Failure Analysis</h3>
            <div className="failures-list">
              {data.summary.failures.map((failure, idx) => (
                <div key={idx} className="failure-item">
                  <span className="skill-name">{failure.skill_name}</span>
                  <span className="failure-count">{failure.failure_count} failures</span>
                  <span className="sources">{failure.sources}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="dashboard-footer">
        <small>Last updated: {new Date(data.generated_at).toLocaleString()}</small>
      </div>
    </div>
  );
};

export default SkillDashboard;
