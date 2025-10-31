import { useState, useEffect } from 'react'
import jackybotTitle from '../../../../assets/images/jackybot_title.png'

function VerticalNav({ cogs, selectedCategory, onSelectCategory }) {
  const [categories, setCategories] = useState([])

  useEffect(() => {
    if (cogs.length > 0) {
      const uniqueCategories = [...new Set(cogs.map(cog => cog.category))]
      const categoriesWithCounts = uniqueCategories.map(cat => ({
        name: cat,
        count: cogs.filter(c => c.category === cat).length,
        icon: getCategoryIcon(cat)
      }))

      // Sort categories with Recently Updated first, then alphabetically
      const sortedCategories = categoriesWithCounts.sort((a, b) => {
        if (a.name === 'Recently Updated') return -1
        if (b.name === 'Recently Updated') return 1
        return a.name.localeCompare(b.name)
      })

      setCategories([
        { name: 'All', count: cogs.length, icon: '📋' },
        ...sortedCategories
      ])
    }
  }, [cogs])

  const getCategoryIcon = (category) => {
    const iconMap = {
      'Recently Updated': '✨',
      'AI': '🤖',
      'Voice': '🎤',
      'Music': '🎶',
      'Text Channels': '📜',
      'Fun': '🎉',
      'Utilities': '🛠️'
    }
    return iconMap[category] || '📦'
  }

  return (
    <div className="w-64 bg-dark-light min-h-screen p-4 border-r border-dark-lighter">
      <div className="mb-8">
        <img
          src={jackybotTitle}
          alt="JackyBot"
          className="h-8 w-auto"
        />
        <p className="text-sm text-gray-400 mt-1">Web UI</p>
      </div>

      <nav className="space-y-2">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-2">
          Categories
        </div>
        {categories.map((category) => (
          <button
            key={category.name}
            onClick={() => onSelectCategory(category.name)}
            className={`
              nav-item w-full text-left
              ${selectedCategory === category.name ? 'active' : ''}
            `}
          >
            <span className="text-xl">{category.icon}</span>
            <span className="flex-1">{category.name}</span>
            <span className="text-sm text-gray-400 bg-dark-lighter px-2 py-0.5 rounded">
              {category.count}
            </span>
          </button>
        ))}
      </nav>
    </div>
  )
}

export default VerticalNav

