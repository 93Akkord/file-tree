"""
https://pypistats.org/packages/akkd-file-tree
"""

import matplotlib.pyplot as plt
import pandas as pd
import pypistats

from tabulate import tabulate


data = pypistats.overall('akkd-file-tree', total=True, format='pandas')

data = data[data['category'] == 'without_mirrors']
grouped = data.groupby('date', as_index=False)['downloads'].sum()


total_downloads = grouped['downloads'].sum()
grouped['total_downloads'] = total_downloads
grouped['percent'] = ((grouped['downloads'] / grouped['total_downloads']) * 100).round(2).astype(str) + '%'


grouped = grouped.drop(columns=['total_downloads'])

total_record = pd.DataFrame({'date': ['Total'], 'downloads': [total_downloads], 'percent': [None]})

grouped = pd.concat([grouped, total_record], ignore_index=True)

grouped = grouped[['date', 'percent', 'downloads']]

output = tabulate(grouped, headers='keys', tablefmt='psql')

print(output)

chart = data.plot(x='date', y='downloads', figsize=(10, 2))

plt.show()

# chart.figure.savefig('overall.png')  # alternatively
